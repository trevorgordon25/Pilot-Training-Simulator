#include <stdio.h>
#include <tchar.h>
#include <strsafe.h>
#include <windows.h>

#define _USE_MATH_DEFINES
#include <math.h>

#include "SimConnect.h"
#include <windows.h>

HANDLE hPipe = INVALID_HANDLE_VALUE;
// Create the pipe before SimConnect_Open in testDataRequest():
void createPipe() {
    hPipe = CreateNamedPipeA(
        "\\\\.\\pipe\\simdata",
        PIPE_ACCESS_OUTBOUND,
        PIPE_TYPE_MESSAGE | PIPE_WAIT,
        1, 4096, 4096, 0, NULL
    );
    if (hPipe == INVALID_HANDLE_VALUE) {
        printf("Failed to create pipe\n");
        return;
    }
    printf("Waiting for Python client to connect...\n");
    ConnectNamedPipe(hPipe, NULL); // blocks until Python connects
    printf("Python client connected!\n");
}


int     quit = 0;
HANDLE hSimConnect = NULL;
enum class ESimState
{
    Stopped,
    Running,
};
ESimState simState = ESimState::Stopped;

struct Struct1
{
    char    title[256];
    double  altitude;
    double  agl;
    double  latitude;
    double  longitude;
    double  bank;
    double  pitch;
    double  headingTrue;
};

enum EVENT_ID
{
    EVENT_SIM_STATE,
    EVENT_RECUR_6HZ,
};

enum DATA_DEFINE_ID
{
    DEFINITION_1,
};

enum DATA_REQUEST_ID 
{
    REQUEST_1,
    REQUEST_2, 
};

void CALLBACK MyDispatchProcRD(SIMCONNECT_RECV* pData, DWORD cbData, void *pContext)
{
    HRESULT hr;
    
    switch(pData->dwID)
    {
        case SIMCONNECT_RECV_ID_EVENT:
        {
            SIMCONNECT_RECV_EVENT *evt = (SIMCONNECT_RECV_EVENT*)pData;

            switch(evt->uEventID)
            {
                case EVENT_SIM_STATE:
                {
                    printf("Sim State: %u\n", evt->dwData);
                    simState = (evt->dwData == 1) ? ESimState::Running : ESimState::Stopped;
                    // If the sim is running, request information on the user aircraft
                    if (simState == ESimState::Running)
                        hr = SimConnect_RequestDataOnSimObjectType(hSimConnect, REQUEST_1, DEFINITION_1, 0, SIMCONNECT_SIMOBJECT_TYPE_USER);
                    break;
                }
                
                case EVENT_RECUR_6HZ:
                {
                    // If the sim is running, request information on the user aircraft
                    if (simState == ESimState::Running)
                        hr = SimConnect_RequestDataOnSimObjectType(hSimConnect, REQUEST_2, DEFINITION_1, 0, SIMCONNECT_SIMOBJECT_TYPE_USER);
                    break;
                }

                default:
                    printf("default event");
                   break;
            }
            break;
        }

        case SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE:
        {
            SIMCONNECT_RECV_SIMOBJECT_DATA_BYTYPE *pObjData = (SIMCONNECT_RECV_SIMOBJECT_DATA_BYTYPE*)pData;
            
            switch(pObjData->dwRequestID)
            {
                case REQUEST_1:
                {
                    DWORD ObjectID = pObjData->dwObjectID;
                    Struct1 *pS = (Struct1*)&pObjData->dwData;
                    if (SUCCEEDED(StringCbLengthA(&pS->title[0], sizeof(pS->title), NULL))) // security check
                    {
                        printf("ObjectID=%d  Title=\"%s\"\nLat=%f  Lon=%f  Alt=%f  AGL=%.2f Bank=%.2f Pitch=%.2f Heading=%.2f\n", 
                            ObjectID, pS->title, pS->latitude, pS->longitude, pS->altitude, pS->agl, pS->bank * 180.0 / M_PI, pS->pitch * 180.0 / M_PI, pS->headingTrue * 180.0 / M_PI);
                    } 
                    break;
                }
                case REQUEST_2:
                {
                    DWORD ObjectID = pObjData->dwObjectID;
                    Struct1 *pS = (Struct1*)&pObjData->dwData;
                    if (SUCCEEDED(StringCbLengthA(&pS->title[0], sizeof(pS->title), NULL)))
                    {
                        char buf[256];
                        // Send a simple CSV line: lat,lon,alt,agl,bank,pitch,heading
                        snprintf(buf, sizeof(buf), "%.6f,%.6f,%.2f,%.2f,%.2f,%.2f,%.2f\n",
                            pS->latitude,
                            pS->longitude,
                            pS->altitude,
                            pS->agl,
                            (pS->bank * 180.0) / M_PI,
                            -1 * (pS->pitch * 180.0) / M_PI,
                            (pS->headingTrue * 180.0) / M_PI);

                        DWORD written;
                        if (hPipe != INVALID_HANDLE_VALUE)
                            WriteFile(hPipe, buf, strlen(buf), &written, NULL);
                    }
                    break;
                }

                default:
                    printf("default data)");
                   break;
            }
            break;
        }

        case SIMCONNECT_RECV_ID_QUIT:
        {
            quit = 1;
            break;
        }

        default:
            printf("Unhandled event received: %d\n",pData->dwID);
            break;
    }
}

void testDataRequest()
{
    HRESULT hr;
    createPipe()
    
    if (SUCCEEDED(SimConnect_Open(&hSimConnect, "Request Data", NULL, 0, 0, 0)))
    {
        printf("Connected to Flight Simulator!\n");

        // Set up the data definition, but do not yet do anything with it
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Title", NULL, SIMCONNECT_DATATYPE_STRING256);
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Altitude", "feet");
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Alt Above Ground", "feet");
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Latitude", "degrees");
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Longitude", "degrees");
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Bank Degrees", "radians");
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Pitch Degrees", "radians");
        hr = SimConnect_AddToDataDefinition(hSimConnect, DEFINITION_1, "Plane Heading Degrees True", "radians");

        // Request an event when the simulation starts or stops
        hr = SimConnect_SubscribeToSystemEvent(hSimConnect, EVENT_SIM_STATE, "Sim");
        hr = SimConnect_SubscribeToSystemEvent(hSimConnect, EVENT_RECUR_6HZ,  "6hz");
  
        printf("We'll request information on the user aircraft whenever the sim becomes active.\n");

        while( 0 == quit )
        {
            SimConnect_CallDispatch(hSimConnect, MyDispatchProcRD, NULL);
            Sleep(10);
        } 

        hr = SimConnect_Close(hSimConnect);
    }
    else
    {
        printf("Unable to connect to Flight Simulator. Exiting.\n");
    }
}

int __cdecl _tmain(int argc, _TCHAR* argv[])
{
    printf("* RequestData sample for Microsoft Flight Simulator *\n");
    testDataRequest();

	return 0;
}