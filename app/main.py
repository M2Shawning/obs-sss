#!/usr/bin/env python
import os
import asyncio, json, base64, binascii
from simpleobsws import WebSocketClient
from simpleobsws import Request as sRequest
from ariadne import QueryType, ObjectType, gql, make_executable_schema
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
GLOBAL_WS_SESSION = None



######## Startup and shutdown functions
async def startup():
    try:
        global GLOBAL_WS_SESSION
        GLOBAL_WS_SESSION = WSSession(os.environ['WS_TARGET_URI'], os.environ['WS_TARGET_PASS'])
        await GLOBAL_WS_SESSION.open()
    except (asyncio.exceptions.TimeoutError) as e:
        print('Error: Could not make websocket connection to:', os.environ['WS_TARGET_URI'])

async def shutdown():
    await GLOBAL_WS_SESSION.close()



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

    async def setCurrentScene(self, name):
        await self.call(sRequest('SetCurrentProgramScene', {'sceneName': name}))



######## Query stuff
type_defs = gql("""
    type Query {
        hello: String!
        run: Int!
        test: Test
    }

    type Test {
        eeee: String!
    }
""")

query = QueryType()
@query.field("hello")
async def resolve_hello(_, info):
    request = info.context["request"]
    user_agent = request.headers.get("user-agent", "guest")
    return "Hello, %s!" % user_agent

@query.field("run")
async def resolve_run(_, info):
    if not info.context["request"].user.is_authenticated:
        return 1
    await GLOBAL_WS_SESSION.setCurrentScene("testScene")
    return 0

@query.field("test")
async def resolve_test(_, info):
    return "aaaa"

test = ObjectType("Test")
@test.field("eeee")
async def resolve_eeee(obj, *_):
    return obj



######## Create executable schema instance
schema = make_executable_schema(type_defs, query, test)
routes = [
    Mount('/graphql', GraphQL(schema)),
    Mount('/', app=StaticFiles(directory='.', html=True))
]
middleware = [
    Middleware(AuthenticationMiddleware, backend=BasicAuthBackend())
]
app = Starlette(debug=True, routes=routes, middleware=middleware, on_startup=[startup], on_shutdown=[shutdown])
