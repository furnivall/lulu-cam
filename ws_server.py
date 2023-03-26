import asyncio
import json
import websockets
from aiortc.contrib.signaling import TcpSocketSignaling

async def handler(websocket, path):
    signaling = TcpSocketSignaling(websocket)

    while True:
        try:
            message = await websocket.recv()
            data = json.loads(message)
            await signaling.send(data)
            data = await signaling.receive()
            await websocket.send(json.dumps(data))
        except websockets.exceptions.ConnectionClosed:
            break

if __name__ == "__main__":
    start_server = websockets.serve(handler, "0.0.0.0", 80)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
