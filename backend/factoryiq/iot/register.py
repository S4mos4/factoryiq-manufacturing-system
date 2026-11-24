"""Register one private ESP32 prototype against existing equipment."""

import argparse
import re

from ..db import engine, query


def register(device,name,equipment):
    if not re.fullmatch(r"esp32-[a-z0-9][a-z0-9-]{0,32}",device):
        raise ValueError("Choose an esp32- device ID with lowercase letters, digits or hyphens.")
    with engine().begin() as conn:
        result=query(conn,"""INSERT INTO iot_devices(id,equipment_id,station_name,station_order,simulated)
                    SELECT :device,id,:name,100,false FROM equipment WHERE code=:equipment
                    ON CONFLICT(id) DO NOTHING RETURNING id""",device=device,name=name,equipment=equipment).scalar()
        if not result:
            raise ValueError("Equipment code was missing or this device ID is already registered.")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device",default="esp32-prototype")
    parser.add_argument("--equipment",required=True)
    parser.add_argument("--name",default="ESP32 bench prototype")
    args=parser.parse_args()
    try:
        print("Registered:",register(args.device,args.name,args.equipment))
    except ValueError as error:
        parser.error(str(error))
