from datetime import datetime, timezone
from fastapi import FastAPI, Request
from pymongo import MongoClient, ASCENDING, DESCENDING
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from models.SingleOperationBody import SingleOperationBody
from typing import List
from models.MultipleOperationBody import MultipleOperationBody
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from zoneinfo import ZoneInfo
from prometheus_fastapi_instrumentator import Instrumentator
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler
import logging
import os, sys

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logger = logging.getLogger("custom_logger")
logging_data = os.getenv("LOG_LEVEL", "INFO").upper()

if logging_data == "DEBUG":
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

# Create a console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logger.level)
formatter = logging.Formatter(
    "%(levelname)s: %(asctime)s - %(name)s - %(message)s"
)
console_handler.setFormatter(formatter)

# Create an instance of the custom handler
loki_handler = LokiLoggerHandler(
    url="http://loki:3100/loki/api/v1/push",
    labels={"application": "FastApi"},
    label_keys={},
    timeout=10,
)

logger.addHandler(loki_handler)
logger.addHandler(console_handler)
logger.info("Logger initialized")

def format_validation_errors(errors, operacion: str = None):
    errores = []
    for err in errors:
        loc_type = err["loc"][0]
        loc_rest = " -> ".join([str(l) for l in err["loc"][1:]])
        input_value = err.get("input", "")
        if loc_rest:
            errores.append(f"Error en {loc_type} -> {loc_rest}: '{input_value}' no es válido.")
        else:
            errores.append(f"Error en {loc_type}: '{input_value}' no es válido.")
    
    respuesta = {"error": errores}
    if operacion:
        respuesta["operacion"] = operacion
    return respuesta

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Error de validación en la solicitud: {format_validation_errors(exc.errors())}")
    return JSONResponse(
        status_code=422,
        content={"detail": format_validation_errors(exc.errors())}
    )

# Conexión a MongoDB
try:
    mongo_client = MongoClient("mongodb://admin_user:web3@mongo:27017", serverSelectionTimeoutMS=5000)
    database = mongo_client["practica1"]
    collection_historial = database["historial"]
    logger.debug("Conexión a MongoDB exitosa")
except Exception as e:
    logger.critical(f"No se pudo conectar a MongoDB: {e}")
    raise RuntimeError("Error crítico: no se pudo conectar a la base de datos")

def check_all_elements_are_numbers(array):
    if type(array) != list:
        return False
    if not all(isinstance(element, (int, float)) for element in array):
        return False
    return True

def check_all_numbers_are_positive(array):
    if check_all_elements_are_numbers(array) == False:
        return False
    
    if not all(element >= 0 for element in array):
        return False
    return True

def return_negative_number_error(operacion: str, numeros: list):

    raise HTTPException(
        status_code=400,
        detail={
            "error": "No se permiten números negativos",
            "operacion": operacion,
            "numerosNegativosEnviados": numeros
        }
    )

def save_in_db(operacion: str, numeros: list, resultado: float):
    document = {
        "resultado": resultado,
        "numeros": numeros,
        "operacion": operacion,
        "date": datetime.now(tz=timezone.utc)
    }

    try:
        collection_historial.insert_one(document)
        logger.debug(f"Documento guardado correctamente en DB: operacion={operacion}, numeros={numeros}, resultado={resultado}")
    except Exception as e:
        logger.critical(f"Fallo al guardar documento en MongoDB: operacion={operacion}, numeros={numeros}, resultado={resultado}, error={e}")
        raise HTTPException(status_code=500, detail="Error interno al guardar operación en la base de datos")

@app.post("/calculadora/sum")
def sumar(body: SingleOperationBody):
    resultado = 0
    if not check_all_numbers_are_positive(body.numeros):
        negativeNumbers = [element for element in body.numeros if element < 0]
        logger.error(f"Se han enviado números negativos en la operación suma: {negativeNumbers}")
        return return_negative_number_error("suma", negativeNumbers)

    for element in body.numeros:
        resultado = resultado + element

    save_in_db("suma", body.numeros, resultado)

    logger.info("Operación suma exitosa")
    logger.debug(f"Operación suma: numeros={body.numeros}, resultado={resultado}")

    return {"numeros": body.numeros, "resultado": resultado, "operacion": "suma"}

@app.post("/calculadora/resta")
def restar(body: SingleOperationBody):  
    if not check_all_numbers_are_positive(body.numeros):
        negativeNumbers = [element for element in body.numeros if element < 0]
        logger.error(f"Se han enviado números negativos en la operación resta: {negativeNumbers}")
        return return_negative_number_error("resta", negativeNumbers)
    
    resultado = body.numeros[0]
    numerosASumar = body.numeros[1:]
    for element in numerosASumar:
        resultado = resultado - element

    save_in_db("resta", body.numeros, resultado)

    logger.info("Operación resta exitosa")
    logger.debug(f"Operación resta: numeros={body.numeros}, resultado={resultado}")

    return {"numeros": body.numeros, "resultado": resultado, "operacion": "resta"}

@app.post("/calculadora/mult")
def multiplicar(body: SingleOperationBody):
    resultado = 1
    if not check_all_numbers_are_positive(body.numeros):
        negativeNumbers = [element for element in body.numeros if element < 0]
        logger.error(f"Se han enviado números negativos en la operación multiplicación: {negativeNumbers}")
        return return_negative_number_error("multiplicacion", negativeNumbers)

    for element in body.numeros:
        resultado = resultado * element

    save_in_db("multiplicacion", body.numeros, resultado)

    logger.info("Operación multiplicación exitosa")
    logger.debug(f"Operación multiplicación: numeros={body.numeros}, resultado={resultado}")

    return {"numeros": body.numeros, "resultado": resultado, "operacion": "multiplicacion"}


@app.post("/calculadora/div")
def dividir(body: SingleOperationBody):
    if not check_all_numbers_are_positive(body.numeros):
        negativeNumbers = [element for element in body.numeros if element < 0]
        logger.error(f"Se han enviado números negativos en la operación división: {negativeNumbers}")
        return return_negative_number_error("division", negativeNumbers)

    resultado = body.numeros[0]
    numerosADividir = body.numeros[1:]

    if 0 in numerosADividir:
        logger.error("Se intentó dividir entre 0")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "No se puede dividir por cero",
                "operacion": "division",
                "numeros": body.numeros
            }
        )

    for element in numerosADividir:
        resultado = resultado / element

    save_in_db("division", body.numeros, resultado)

    logger.info("Operación división exitosa")
    logger.debug(f"Operación división: numeros={body.numeros}, resultado={resultado}")

    return {"numeros": body.numeros, "resultado": resultado, "operacion": "division"}

@app.post("/calculadora/operacionMultiple")
def multiple_operacion(operations: MultipleOperationBody):
    responses = []
    has_error = False

    for operation in operations.operaciones:
        try:
    
            singleOperation = SingleOperationBody(numeros=operation.numeros)

            if operation.operacion == "suma":
                responses.append(sumar(singleOperation))
            elif operation.operacion == "resta":
                responses.append(restar(singleOperation))
            elif operation.operacion == "multiplicacion":
                responses.append(multiplicar(singleOperation))
            elif operation.operacion == "division":
                responses.append(dividir(singleOperation))
            else:
                logger.error(f"Se intentó realizar una operación no válida en operación múltiple: {operacion}")
                has_error = True
                responses.append({
                    "error": "Operacion no soportada",
                    "operacion": operation.operacion,
                    "numeros": operation.numeros
                })

        except ValidationError as e:
            has_error = True
            responses.append(format_validation_errors(e.errors(), operation.operacion))
            logger.error(f"Error de validación en operación múltiple: {format_validation_errors(e.errors(), operation.operacion)}")
        except HTTPException as e:
            has_error = True
            responses.append(e.detail)
            logger.error(f"Error HTTP en operación múltiple: {e.detail}")

    status_code = 206 if has_error else 200
    return JSONResponse(content=responses, status_code=status_code)



@app.get("/calculadora/historial")
def obtener_historial(
    operacion: str = None,
    fecha: datetime = None,
    ordenarPor: str = None,
    orden: str = None
):
    if operacion and operacion not in ("suma", "resta", "multiplicacion", "division"):
        logger.error(f"Se intentó filtrar por una operación no válida: {operacion}")
        raise HTTPException(
            status_code=400,
            detail={"error": "Operacion no soportada", "operacion": operacion}
        )

    if fecha and type(fecha) != datetime:
        logger.error(f"La fecha proporcionada para filtrar no era válida: {fecha}")
        raise HTTPException(
            status_code=400,
            detail={"error": "Fecha no valida", "fecha": fecha}
        )

    if ordenarPor and ordenarPor not in ("date", "resultado"):
        logger.error(f"Se ordenar por un tipo de dato no soportado: {ordenarPor}")
        raise HTTPException(
            status_code=400,
            detail={"error": "Ordenar por no soportado", "ordenarPor": ordenarPor}
        )

    if orden and orden not in ("asc", "desc"):
        logger.error(f"Se ordenar por un tipo de orden no soportado: {orden}")
        raise HTTPException(
            status_code=400,
            detail={"error": "Orden no soportado", "orden": orden}
        )

    filtro = {}

    if operacion:
        filtro["operacion"] = operacion

    if fecha:
        # Interpretar la fecha como hora de México
        tz_mex = ZoneInfo("America/Mexico_City")

        inicio_mex = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0, tzinfo=tz_mex)
        fin_mex = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59, tzinfo=tz_mex)

        inicio_utc = inicio_mex.astimezone(ZoneInfo("UTC"))
        fin_utc = fin_mex.astimezone(ZoneInfo("UTC"))

        filtro["date"] = {"$gte": inicio_utc, "$lt": fin_utc}

    orden_mongo = ASCENDING if orden == "asc" else DESCENDING
    sort = [(ordenarPor, orden_mongo)] if ordenarPor else None

    cursor = collection_historial.find(filtro)
    if sort:
        cursor = cursor.sort(sort)

    historial = []
    for doc in cursor:
        fecha_mex = doc["date"].astimezone(ZoneInfo("America/Mexico_City"))
        historial.append({
            "numeros": doc["numeros"],
            "resultado": doc["resultado"],
            "date": fecha_mex.isoformat(),
            "operacion": doc["operacion"]
        })

    logger.info(
        f"Historial obtenido. Filtros: operacion={operacion}, fecha={fecha}, ordenarPor={ordenarPor}, orden={orden}"
    )

    logger.debug(f"Historial obtenido: {historial}")

    return {"historial": historial}

Instrumentator().instrument(app).expose(app)