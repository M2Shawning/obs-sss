#!/usr/bin/env python
import os, logging, traceback
import asyncio, json, base64, binascii
from simpleobsws import WebSocketClient
from simpleobsws import Request as sRequest
from ariadne import QueryType, MutationType, ObjectType, gql, make_executable_schema
from ariadne.asgi import GraphQL
from starlette.applications import Starlette
from starlette.authentication import (
    AuthCredentials, AuthenticationBackend, AuthenticationError, SimpleUser
)
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles



######## Global vars
GLOBAL_WS_SESSION_DICT = {}



######## Startup and shutdown functions
async def startup():
        wsTargetList = json.loads(os.environ['WS_TARGET_LIST'])
        await asyncio.gather(*map(openWSSession, wsTargetList))

async def shutdown():
    for ws in GLOBAL_WS_SESSION_DICT.values():
        await ws.close()



######## Auth functions
class BasicAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        if "Authorization" not in conn.headers:
            return

        auth = conn.headers["Authorization"]
        try:
            scheme, credentials = auth.split()
            if scheme.lower() != 'basic':
                return
            decoded = base64.b64decode(credentials).decode("ascii")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationError('Invalid basic auth credentials')

        username, _, password = decoded.partition(":")
        if username == os.environ['API_USER'] and password == os.environ['API_PASS']:
            return AuthCredentials(["authenticated"]), SimpleUser(username)



######## Cool functions
class WSSession(WebSocketClient):
    async def open(self):
        await self.connect()
        await self.wait_until_identified()

    async def close(self):
        await self.disconnect()

    def getURL(self):
        return self.url

    async def setCurrentScene(self, name):
        await self.call(sRequest('SetCurrentProgramScene', {'sceneName': name}))

async def openWSSession(wsTarget):
    global GLOBAL_WS_SESSION_DICT
    try:
        hostName = wsTarget['hostName']
        ws = WSSession(wsTarget['url'], wsTarget['password'])
        await ws.open()
        if hostName in GLOBAL_WS_SESSION_DICT:
            GLOBAL_WS_SESSION_DICT[hostName].close()
        GLOBAL_WS_SESSION_DICT[hostName] = ws
    except (asyncio.exceptions.TimeoutError) as e:
        print('Error: Could not make websocket connection to:', hostName)



######## Query stuff
type_defs = gql("""
    type Query {
        hello: String!
    }

    type Mutation {
        setCurrentScene(hostName: String!, sceneName: String!): Boolean!
    }
""")

query = QueryType()
@query.field("hello")
async def resolve_hello(_, info):
    request = info.context["request"]
    user_agent = request.headers.get("user-agent", "guest")
    return "Hello, %s!" % user_agent

mutation = MutationType()
@mutation.field("setCurrentScene")
async def resolve_setCurrentScene(_, info, hostName, sceneName):
    if not info.context["request"].user.is_authenticated:
        return 1
    try:
        await GLOBAL_WS_SESSION_DICT[hostName].setCurrentScene(sceneName)
    except Exception as e:
        print("Error: Could not set scene", sceneName, "on host", hostName)
        logging.error(traceback.format_exc())
        print(e)
        return 1
    return 0



######## Create executable schema instance
schema = make_executable_schema(type_defs, query, mutation)
routes = [
    Mount('/graphql', GraphQL(schema)),
    Mount('/', app=StaticFiles(directory='.', html=True))
]
middleware = [
    Middleware(AuthenticationMiddleware, backend=BasicAuthBackend())
]
app = Starlette(debug=True, routes=routes, middleware=middleware, on_startup=[startup], on_shutdown=[shutdown])
