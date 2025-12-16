Aquí tienes el archivo completo. Solo tienes que copiar el bloque de código y pegarlo en tu archivo `README.md`.

````markdown
# 🎴 Osuno API Documentation

Documentación oficial del backend para el proyecto **Osuno**. Esta API da servicio a la aplicación móvil (Android) y al cliente de juego (Godot).

## 📋 Tabla de Contenidos
1. [Autenticación](#autenticación)
2. [Usuarios](#usuarios)
3. [Salas (Lobby)](#salas-lobby)
4. [Mecánicas del Juego (Game Loop)](#mecánicas-del-juego-game-loop)
5. [Lógica de Negocio y Reglas](#lógica-de-negocio-y-reglas)

---

## Autenticación

La mayoría de los endpoints protegidos requieren el token de sesión en las cabeceras.

| Header | Valor | Descripción |
| :--- | :--- | :--- |
| `Session` | `{sessionToken}` | Token recibido tras hacer login (`/sessions`). |

---

## Usuarios

### 1. Registrar Usuario
Crea una nueva cuenta.
* **Uso:** Exclusivo App Android.
* **Método:** `POST`
* **Endpoint:** `/users`

**Request Body:**
```json
{
  "username": "paco",
  "password": "1234"
}
````

**Respuestas:**

  * `201 Created`: Usuario creado exitosamente.
  * `400 Bad Request`: Datos inválidos o faltantes.
  * `409 Conflict`: El nombre de usuario ya existe.

### 2\. Iniciar Sesión (Login)

Autentica al usuario y devuelve el token de sesión.

  * **Uso:** App Android y Godot.
  * **Método:** `POST`
  * **Endpoint:** `/sessions`

**Request Body:**

```json
{
  "username": "paco",
  "password": "1234"
}
```

**Respuestas:**

  * `201 Created`: Login correcto.
    ```json
    {
      "sessionToken": "asdflaksjasfd"
    }
    ```
  * `400 Bad Request`: Formato incorrecto.
  * `401 Unauthorized`: Contraseña o usuario incorrectos.

### 3\. Obtener Perfil

Obtiene las estadísticas del jugador actual.

  * **Uso:** App Android (Pantalla de perfil).
  * **Método:** `GET`
  * **Endpoint:** `/users/me`
  * **Headers:** `Session`

**Respuestas:**

  * `200 OK`:
    ```json
    {
      "username": "User1001238",
      "gamesWon": 2,
      "gamesPlayed": 200
    }
    ```
  * `401 Unauthorized`: Token inválido o expirado.

> **Nota sobre Rangos:** El backend no devuelve el rango (Bronce/Plata/etc). El cliente debe calcularlo basándose en `gamesWon` y `gamesPlayed`. Ver sección [Lógica de Rangos](https://www.google.com/search?q=%23c%C3%A1lculo-de-rangos).

-----

## Salas (Lobby)

### 4\. Crear Sala

Crea una nueva partida y devuelve el código de acceso.

  * **Método:** `POST`
  * **Endpoint:** `/room`
  * **Headers:** `Session`

**Respuestas:**

  * `201 Created`:
    ```json
    {
      "roomCode": "XVJ"
    }
    ```
  * `401 Unauthorized`: Token inválido.

### 5\. Unirse a Sala

Permite a un segundo jugador entrar a una sala existente.

  * **Método:** `POST`
  * **Endpoint:** `/room/{roomCode}`
  * **Headers:** `Session`

**Respuestas:**

  * `200 OK`: Unido correctamente.
  * `401 Unauthorized`: Token inválido.
  * `403 Forbidden`: No te puedes unir (ej. la sala ya está llena con 2 jugadores).
  * `404 Not Found`: El código de sala no existe.

### 6\. Polling de Sala (Espera)

Consulta el estado de la sala mientras esperas al rival.

  * **Frecuencia recomendada:** Cada 3 segundos.
  * **Método:** `GET`
  * **Endpoint:** `/room/{roomCode}`
  * **Headers:** `Session`

**Respuestas:**

  * `200 OK`:
    ```json
    {
      "status": "waiting"     
    }
    ```
    o bien:
    ```json
    {
      "status": "gameStarted"  
    }
    ```

-----

## Mecánicas del Juego (Game Loop)

### Reglas Básicas

  * **Cartas:** Colores (red, green, yellow, blue) y números (1-10).
  * **Mano inicial:** 5 cartas.
  * **Sin especiales:** No hay +4, reversos, ni saltos de turno.
  * **Objetivo:** Quedarse sin cartas.

### 7\. Polling del Estado del Juego

Obtiene la "foto" actual de la partida. Debe llamarse al inicio y cada 3 segundos si `isYourTurn` es `false`.

  * **Método:** `GET`
  * **Endpoint:** `/game/{roomCode}`
  * **Headers:** `Session`

**Respuestas:**

  * `200 OK`:
    ```json
    {
      "yourHand": ["blue4", "red3", "yellow1", "green10", "green9"],
      "tableCard": "red3",    // "none" si acaba de empezar
      "isYourTurn": true,     // true = habilita UI para jugar/robar
      "gameFinished": "no"    // "no" | "youWon" | "youLost"
    }
    ```
  * `401 Unauthorized`: Token inválido.
  * `403 Forbidden`: No perteneces a esta partida.
  * `404 Not Found`: Partida no encontrada.

### 8\. Jugar Carta

Intenta colocar una carta de tu mano en la mesa.

  * **Método:** `POST`
  * **Endpoint:** `/game/{roomCode}/tableCard`
  * **Headers:** `Session`

**Request Body:**

```json
{
  "cardToPlay": "blue4"
}
```

**Respuestas:**

  * `201 Created`: Carta jugada, turno finalizado.
  * `403 Forbidden`:
      * No es tu turno.
      * No tienes esa carta.
      * La carta no coincide en color o número con la `tableCard`.
  * `404 Not Found`: `roomCode` inválido.

### 9\. Robar Carta

Roba una carta del mazo. **Importante:** Esta acción NO pasa el turno automáticamente. El jugador debe intentar jugar la carta robada si es posible.

  * **Método:** `POST`
  * **Endpoint:** `/game/{roomCode}/deck`
  * **Headers:** `Session`

**Respuestas:**

  * `200 OK`: Carta robada. El cliente debe hacer un *poll* (`GET /game/...`) inmediatamente para ver su nueva mano.
  * `403 Forbidden`: No hay cartas en el mazo (ver lógica de fin de juego más abajo).

-----

## Lógica de Negocio y Reglas

### Fin de Juego por Mazo Vacío

El mazo **no se recicla** (no se da la vuelta a los descartes). Si el mazo se vacía:

1.  El servidor comprueba si el jugador actual puede jugar algo de su mano.
2.  Si no puede jugar, comprueba si el rival puede jugar.
3.  Si nadie puede jugar o no quedan cartas para robar y jugar, **Game Over**.
4.  Gana quien tenga **menos cartas** en la mano.

<!-- end list -->
