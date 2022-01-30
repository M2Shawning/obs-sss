#!/usr/bin/env python
import os
import asyncio, json
import simpleobsws
from ariadne import QueryType, ObjectType, gql, make_executable_schema
from ariadne.asgi import GraphQL
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles



######## Global vars
GLOBAL_WS_SESSION = None



######## Startup and shutdown functions
async def startup():
    global GLOBAL_WS_SESSION
    GLOBAL_WS_SESSION = WSSession(os.environ['WS_TARGET_URI'], os.environ['WS_TARGET_PASS'])
    await GLOBAL_WS_SESSION.open()

async def shutdown():
    global GLOBAL_WS_SESSION
    await GLOBAL_WS_SESSION.close()



######## Cool functions
class WSSession():
    def __init__(self, uri, password):
        self.uri = uri
        self.password = password

        self.ws = simpleobsws.WebSocketClient(uri, password)
    
    async def open(self):
        await self.ws.connect()
        await self.ws.wait_until_identified()

    async def close(self):
        await self.ws.disconnect()

    def getRawSession(self):
        return self.ws



async def test_function():
    ws = GLOBAL_WS_SESSION.getRawSession()

    #response = await ws.call(simpleobsws.Request('GetSceneList'))
    #print(response)

    for i in range(2):
        await ws.call(simpleobsws.Request('SetCurrentProgramScene', {'sceneName': 'testScene'}))
        await asyncio.sleep(1)
        await ws.call(simpleobsws.Request('SetCurrentProgramScene', {'sceneName': 'Scene'}))
        await asyncio.sleep(1)



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
    await test_function()
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
    Mount('/api/v1', GraphQL(schema)),
    Mount('', app=StaticFiles(directory='.', html=True))
]
app = Starlette(routes=routes, debug=True, on_startup=[startup], on_shutdown=[shutdown])
