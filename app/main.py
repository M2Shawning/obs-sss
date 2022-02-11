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
import motor.motor_asyncio



######## Global vars
GLOBAL_WS_SESSION_DICT = {}
GLOBAL_OBS_SHOW_DICT = {}
DBCLIENT = None
DB = None



######## Startup and shutdown functions
async def startup():
        await dbInit(os.environ['MONGODB_URL'])
        await loadOBSSessions()
        await loadAllOBSShows()

async def shutdown():
    for ws in GLOBAL_WS_SESSION_DICT.values():
        await ws.close()

async def dbInit(connString):
    global DBCLIENT
    global DB
    DBCLIENT = motor.motor_asyncio.AsyncIOMotorClient(connString, serverSelectionTimeoutMS=5000)

    try:
        await DBCLIENT.server_info()
    except Exception:
        print("Error: Unable to connect to the mongodb server.")

    DB = DBCLIENT['obs-sss']

async def loadOBSSessions():
    global GLOBAL_WS_SESSION_DICT

    c = DB['obs_hosts']
    async for obsHost in c.find({}):
        try:
            hostName = obsHost['hostName']
            ws = WSSession(obsHost['url'], obsHost['password'])
            await ws.open()
            if hostName in GLOBAL_WS_SESSION_DICT:
                await GLOBAL_WS_SESSION_DICT[hostName].close()
            GLOBAL_WS_SESSION_DICT[hostName] = ws
        except (asyncio.exceptions.TimeoutError) as e:
            print('Error: Could not make websocket connection to:', hostName)

async def loadAllOBSShows():
    c = DB['obs_shows']
    async for d in c.find({}, {'showName': 1}):
        await loadOBSShow(d['showName'])



######## CRUD and loading/unloading
async def loadOBSShow(showName):
    global GLOBAL_OBS_SHOW_DICT

    c = DB['obs_shows']
    d = await readOBSShow(showName)
    obsShow = OBSShow()
    for rawOBSState in d['obsStateList']:
        obsShow.add(OBSState(rawOBSState['hostName'], rawOBSState['sceneName']))
    GLOBAL_OBS_SHOW_DICT[showName] = obsShow

async def unloadOBSShow(showName):
    global GLOBAL_OBS_SHOW_DICT
    GLOBAL_OBS_SHOW_DICT.pop(showName)

# Read obs show entry
async def readOBSShow(showName):
    c = DB['obs_shows']
    return await c.find_one({'showName': showName})

# Create or update obs show entry
async def configureOBSShow():
    c = DB['obs_shows']

    # Add code

# Delete obs show entry
async def deleteOBSShow():
    c = DB['obs_shows']

    # Code



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

    async def getURL(self):
        return self.url

    async def setCurrentScene(self, name):
        await self.call(sRequest('SetCurrentProgramScene', {'sceneName': name}))

class OBSState():
    def __init__(self, hostName, sceneName):
        self.hostName = hostName
        self.sceneName = sceneName

class OBSShow():
    def __init__(self):
        self.obsStateList = []

    def add(self, obsState):
        self.obsStateList.append(obsState)
    
    async def execute(self):
        for obsState in self.obsStateList:
            if obsState.hostName in GLOBAL_WS_SESSION_DICT:
                await GLOBAL_WS_SESSION_DICT[obsState.hostName].setCurrentScene(obsState.sceneName)
            else:
                print('Error: Could not execute on', obsState.hostName, 'as one of the configured key values doesn\'t exist')



######## Query stuff
type_defs = gql("""
    type Query {
        hello: String!
        getShowNames: [String]!
    }

    type Mutation {
        setCurrentScene(hostName: String!, sceneName: String!): Boolean!
        executeShow(showName: String!): Boolean!
        reconnectAllWS: Boolean!
    }
""")

query = QueryType()
@query.field("hello")
async def resolve_hello(_, info):
    request = info.context["request"]
    user_agent = request.headers.get("user-agent", "guest")
    return "Hello, %s!" % user_agent

@query.field("getShowNames")
async def resolve_getShowNames(_, info):
    if not info.context["request"].user.is_authenticated:
        return "Invalid authentication"
    global GLOBAL_OBS_SHOW_DICT
    return list(GLOBAL_OBS_SHOW_DICT.keys())

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

@mutation.field("executeShow")
async def resolve_executeShow(_, info, showName):
    if not info.context["request"].user.is_authenticated:
        return 1
    try:
        await GLOBAL_OBS_SHOW_DICT[showName].execute()
    except Exception as e:
        print("Error: Could not execute show", showName)
        logging.error(traceback.format_exc())
        print(e)
        return 1
    return 0

@mutation.field("reconnectAllWS")
async def resolve_executeShow(_, info):
    if not info.context["request"].user.is_authenticated:
        return 1
    wsTargetList = json.loads(os.environ['WS_TARGET_LIST'])
    await asyncio.gather(*map(openWSSession, wsTargetList))
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
