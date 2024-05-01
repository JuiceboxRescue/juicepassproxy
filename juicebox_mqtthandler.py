import asyncio
import logging
import re
import sys

from const import VERSION
from ha_mqtt_discoverable import DeviceInfo, Settings
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo, Text, TextInfo
from paho.mqtt.client import Client, MQTTMessage

# import sys


logger = logging.getLogger(__name__)


class JuiceboxMQTTEntity:
    def __init__(
        self,
        name,
        **kwargs,
    ):
        # logger.debug(f"Entity Init: {name}")
        self.name = name
        self.kwargs = kwargs
        self.unique_id = f"{self.kwargs.get("juicebox_id", None)} {self.name}"
        self.experimental = self.kwargs.get("experimental", False)
        self.state = None
        self.attributes = {}
        self._mqtt = None
        self.loop = asyncio.get_running_loop()
        self._mitm_handler = self.kwargs.get("mitm_handler", None)
        if self._mitm_handler:
            logger.debug(f"mitm_handler type: {self._mitm_handler}")

    def add_kwargs(self, **kwargs):
        self.kwargs.update(kwargs)
        self.unique_id = f"{self.kwargs.get("juicebox_id", None)} {self.name}"
        self.experimental = self.kwargs.get("experimental", False)
        self._mitm_handler = self.kwargs.get("mitm_handler", None)
        if self._mitm_handler:
            logger.debug(f"mitm_handler type: {self._mitm_handler}")

    async def set_state(self, state=None):
        self.state = state
        try:
            self._mqtt.set_state(state)
        except AttributeError as e:
            logger.warning(
                f"Can't update state for {
                    self.name} as MQTT isn't connected/started. ({e.__class__.__qualname__}: {e})"
            )

    async def set_attributes(self, attr={}):
        self.attributes = attr
        try:
            self._mqtt.set_attributes(attr)
        except AttributeError as e:
            logger.warning(
                f"Can't update attribtutes for {
                    self.name} as MQTT isn't connected/started. ({e.__class__.__qualname__}: {e})"
            )


class JuiceboxMQTTSensor(JuiceboxMQTTEntity):

    def __init__(
        self,
        name,
        **kwargs,
    ):
        # logger.debug(f"Sensor Init: {name}")
        self.ent_type = "sensor"
        super().__init__(name, **kwargs)

    async def start(self):
        # logger.debug(f"JuiceboxMQTTSensor Function: {sys._getframe().f_code.co_name}")

        self._mqtt = Sensor(
            Settings(
                mqtt=self.kwargs.get("mqtt", self.kwargs.get("mqtt_settings", None)),
                entity=SensorInfo(
                    name=self.name,
                    unique_id=self.unique_id,
                    icon=self.kwargs.get("icon", None),
                    state_class=self.kwargs.get("state_class", None),
                    device_class=self.kwargs.get("device_class", None),
                    unit_of_measurement=self.kwargs.get("unit_of_measurement", None),
                    entity_category=self.kwargs.get("entity_category", None),
                    expire_after=self.kwargs.get("expire_after", None),
                    enabled_by_default=self.kwargs.get("enabled_by_default", True),
                    device=self.kwargs.get(
                        "device", self.kwargs.get("device_info", None)
                    ),
                ),
            )
        )

        if self.kwargs.get("initial_state", None) is not None:
            await self.set_state(self.kwargs.get("initial_state", None))
        # logger.debug(f"Started Sensor: {self.name}. MQTT: {self._mqtt}")


class JuiceboxMQTTText(JuiceboxMQTTEntity):

    def __init__(
        self,
        name,
        **kwargs,
    ):
        logger.debug(f"Text Init: {name}")
        self.ent_type = "text"
        super().__init__(name, **kwargs)

    async def start(self):
        logger.debug(f"JuiceboxMQTTText Function: {sys._getframe().f_code.co_name}")

        self.callback = self.kwargs.get("callback", self.default_callback)

        self._mqtt = Text(
            Settings(
                mqtt=self.kwargs.get("mqtt", self.kwargs.get("mqtt_settings", None)),
                entity=TextInfo(
                    name=self.name,
                    unique_id=self.unique_id,
                    device=self.kwargs.get(
                        "device", self.kwargs.get("device_info", None)
                    ),
                    icon=self.kwargs.get("icon", None),
                    device_class=self.kwargs.get("device_class", None),
                    unit_of_measurement=self.kwargs.get("unit_of_measurement", None),
                    entity_category=self.kwargs.get("entity_category", None),
                    expire_after=self.kwargs.get("expire_after", None),
                    enabled_by_default=self.kwargs.get("enabled_by_default", True),
                ),
            ),
            command_callback=self.callback,
            user_data=self.kwargs.get("user_data", None),
        )

        if self.kwargs.get("initial_text", None) is not None:
            # logger.debug("sending initial_text")
            await self.set_text(self.kwargs.get("initial_text", None))
        else:
            await self.set_text(self.name)
        logger.debug(f"Started Text: {self.name}. MQTT: {self._mqtt}")

    async def set_state(self, state=None):
        await self.set_text(state)

    async def set_text(self, text=None):
        self.state = text
        try:
            self._mqtt.set_text(text)
            logger.debug(f"Set Text ({self.name}): {text}")
        except AttributeError as e:
            logger.warning(
                f"Can't update text for {
                    self.name} as MQTT isn't connected/started. ({e.__class__.__qualname__}: {e})"
            )

    def default_callback(self, client: Client, user_data, message: MQTTMessage):
        self.loop.create_task(self.default_callback_async(client, user_data, message))

    async def default_callback_async(
        self, client: Client, user_data, message: MQTTMessage
    ):
        text = message.payload.decode()
        logger.info(f"Text Callback ({self.name}): {text}. User Data: {user_data}")
        if self._mitm_handler:
            logger.debug(f"Sending to MITM: {text}")
            await self._mitm_handler.send_data_to_juicebox(bytes(text, "utf-8"))
        else:
            logger.debug(
                f"Cannot send to MITM. mitm_handler type: {type(self._mitm_handler)}"
            )
        await self.set_text(text)


class JuiceboxMQTTHandler:
    def __init__(
        self,
        device_name,
        mqtt_settings,
        experimental,
        juicebox_id=None,
        mitm_handler=None,
        loglevel=None,
    ):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        if loglevel is not None:
            logger.setLevel(loglevel)
        self.mqtt_settings = mqtt_settings
        self.device_name = device_name
        self.juicebox_id = juicebox_id
        self._mitm_handler = mitm_handler
        self.experimental = experimental

        self.device_info = DeviceInfo(
            name=self.device_name,
            identifiers=(
                [self.juicebox_id]
                if self.juicebox_id is not None
                else [self.device_name]
            ),
            connections=[
                (
                    ["JuiceBox ID", self.juicebox_id]
                    if self.juicebox_id is not None
                    else []
                )
            ],
            manufacturer="EnelX",
            model="JuiceBox",
            sw_version=VERSION,
            via_device="JuicePass Proxy",
        )
        self.entities = {
            "status": JuiceboxMQTTSensor(
                name="Status",
                icon="mdi:ev-station",
            ),
            "current": JuiceboxMQTTSensor(
                name="Current",
                state_class="measurement",
                device_class="current",
                unit_of_measurement="A",
            ),
            "current_rating": JuiceboxMQTTSensor(
                name="Current Rating",
                state_class="measurement",
                device_class="current",
                unit_of_measurement="A",
            ),
            "frequency": JuiceboxMQTTSensor(
                name="Frequency",
                state_class="measurement",
                device_class="frequency",
                unit_of_measurement="Hz",
            ),
            "energy_lifetime": JuiceboxMQTTSensor(
                name="Energy (Lifetime)",
                state_class="total_increasing",
                device_class="energy",
                unit_of_measurement="Wh",
            ),
            "energy_session": JuiceboxMQTTSensor(
                name="Energy (Session)",
                state_class="total_increasing",
                device_class="energy",
                unit_of_measurement="Wh",
            ),
            "temperature": JuiceboxMQTTSensor(
                name="Temperature",
                state_class="measurement",
                device_class="temperature",
                unit_of_measurement="°F",
            ),
            "voltage": JuiceboxMQTTSensor(
                name="Voltage",
                state_class="measurement",
                device_class="voltage",
                unit_of_measurement="V",
            ),
            "power": JuiceboxMQTTSensor(
                name="Power",
                state_class="measurement",
                device_class="power",
                unit_of_measurement="W",
            ),
            "debug_message": JuiceboxMQTTSensor(
                name="Last Debug Message",
                expire_after=60,
                enabled_by_default=False,
                icon="mdi:bug",
                entity_category="diagnostic",
                initial_state=f"INFO: Starting JuicePass Proxy {VERSION}",
            ),
            "local_data": JuiceboxMQTTSensor(
                name="Local Data",
                experimental=True,
                enabled_by_default=False,
                entity_category="diagnostic",
            ),
            "remote_data": JuiceboxMQTTSensor(
                name="Remote Data",
                experimental=True,
                enabled_by_default=False,
                entity_category="diagnostic",
            ),
            "send_local": JuiceboxMQTTText(
                name="Send Local Command",
                experimental=True,
                enabled_by_default=False,
                entity_category="diagnostic",
            ),
        }
        for entity in self.entities.values():
            # logger.debug(f"Adding extras to: {entity.name} (type: {entity.ent_type})")
            entity.add_kwargs(
                juicebox_id=self.juicebox_id,
                device_info=self.device_info,
                mqtt_settings=self.mqtt_settings,
            )
            if entity.ent_type in ["text"]:
                logger.debug(
                    f"Adding mitm_handler ({type(self._mitm_handler)}) to: {
                        entity.name} (type: {entity.ent_type})"
                )
                entity.add_kwargs(mitm_handler=self._mitm_handler)

    async def start(self):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        logger.info("Starting JuiceboxMQTTHandler")

        gather_list = []
        for entity in self.entities.values():
            if entity.experimental is False or self.experimental is True:
                # logger.debug(f"MQTT Gather: {entity.name}")
                gather_list.append(asyncio.create_task(entity.start()))
        await asyncio.gather(
            *gather_list,
            return_exceptions=True,
        )

    async def set_mitm_handler(self, mitm_handler):
        logger.debug(f"mitm_handler type: {type(mitm_handler)}")

        self._mitm_handler = mitm_handler
        for entity in self.entities.values():
            if entity.ent_type in ["text"]:
                logger.debug(
                    f"Adding mitm_handler ({type(self._mitm_handler)}) to: {
                        entity.name} (type: {entity.ent_type})"
                )
                entity.add_kwargs(mitm_handler=mitm_handler)

    async def basic_message_parse(self, data: bytes):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        message = {"type": "basic"}
        message["current"] = 0
        message["energy_session"] = 0
        message["current_max"] = 0
        message["current_max_charging"] = 0
        message["current_rating"] = 0
        active = True
        parts = re.split(r",|!|:", data.decode("utf-8"))
        parts.pop(0)  # JuiceBox ID
        parts.pop(-1)  # Ending blank
        parts.pop(-1)  # Checksum

        # Undefined parts: F, e, r, b, B, P, p
        # https://github.com/snicker/juicepassproxy/issues/52
        # s = Counter
        # v = version of protocol
        # i = Interval number. It contains a 96-slot interval memory (15-minute x 24-hour cycle) and
        #   this tells you how much energy was consumed in the rolling window as it reports one past
        #   (or current, if it's reporting the "right-now" interval) interval per message.
        #   The letter after "i" = the energy in that interval (usually 0 if you're not charging basically 24/7)
        # t - probably the report time in seconds - "every 9 seconds" (or may end up being 10).
        #   It can change its reporting interval if the bit mask in the reply command indicates that it should send reports faster (yet to be determined).
        # u - loop counter
        for part in parts:
            if part[0] == "S":
                message["status"] = {
                    "S0": "Unplugged",
                    "S1": "Plugged In",
                    "S2": "Charging",
                    "S5": "Error",
                    "S00": "Unplugged",
                    "S01": "Plugged In",
                    "S02": "Charging",
                    "S05": "Error",
                }.get(part)
                if message["status"] is None:
                    message["status"] = f"unknown {part}"
                active = message["status"].lower() == "charging"
            elif part[0] == "A" and active:
                message["current"] = round(float(part.split("A")[1]) * 0.1, 2)
            elif part[0] == "m":
                message["current_rating"] = float(part.split("m")[1])
            elif part[0] == "M":
                message["current_max"] = float(part.split("M")[1])
            elif part[0] == "C":
                message["current_max_charging"] = float(part.split("C")[1])
            elif part[0] == "f":
                message["frequency"] = round(float(part.split("f")[1]) * 0.01, 2)
            elif part[0] == "L":
                message["energy_lifetime"] = float(part.split("L")[1])
            elif part[0] == "v":
                message["protocol_version"] = part.split("v")[1]
            elif part[0] == "E" and active:
                message["energy_session"] = float(part.split("E")[1])
            elif part[0] == "t":
                message["report_time"] = part.split("t")[1]
            elif part[0] == "v":
                message["protocol_version"] = part.split("v")[1]
            elif part[0] == "i":
                message["interval"] = part.split("i")[1]
            elif part[0] == "u":
                message["loop_counter"] = part.split("u")[1]
            elif part[0] == "T":
                message["temperature"] = round(float(part.split("T")[1]) * 1.8 + 32, 2)
            elif part[0] == "V":
                message["voltage"] = round(float(part.split("V")[1]) * 0.1, 2)
            else:
                message["unknown_" + part[0]] = part[1:]
        message["power"] = round(
            message.get("voltage", 0) * message.get("current", 0), 2
        )
        message["local_data"] = data.decode("utf-8")
        return message

    async def udp_mitm_oserror_message_parse(self, data):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        message = {"type": "udp_mitm_oserror"}
        err_data = str(data).split("|")
        message["status"] = "unavailable"
        message["debug_message"] = (
            f"JuiceboxMITM {err_data[1].title()} OSError {err_data[3]} [{
                err_data[2]}]: {err_data[4]}"
        )
        return message

    async def debug_message_parse(self, data):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        message = {"type": "debug"}
        dbg_data = (
            str(data)
            .replace("https://", "https//")
            .replace("http://", "http//")
            .split(":")
        )
        dbg_level_abbr = dbg_data[1].split(",")[1]
        if dbg_level_abbr == "NFO":
            dbg_level = "INFO"
        elif dbg_level_abbr == "WRN":
            dbg_level = "WARNING"
        elif dbg_level_abbr == "ERR":
            dbg_level = "ERROR"
        else:
            dbg_level = dbg_level_abbr
        dbg_msg = (
            dbg_data[2].replace("https//", "https://").replace("http//", "http://")
        )
        message["debug_message"] = f"{dbg_level}: {dbg_msg}"
        return message

    async def basic_message_publish(self, message):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        logger.debug(f"Publish {message.get('type').title()} Message: {message}")

        try:
            attributes = {}
            for k in message:
                entity = self.entities.get(k, None)
                if entity and (
                    entity.experimental is False or self.experimental is True
                ):
                    await entity.set_state(message.get(k, None))
                attributes[k] = message.get(k, None)
            if self.experimental and self.entities.get("local_data", None) is not None:
                await self.entities.get("local_data").set_attributes(attributes)
        except Exception as e:
            logger.exception(
                f"Failed to publish sensor data to MQTT. ({e.__class__.__qualname__}: {
                    e})"
            )

    async def remote_mitm_handler(self, data):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")

        try:
            logger.debug(f"Remote: {data}")
            if self.experimental and self.entities.get("remote_data", None) is not None:
                await self.entities.get("remote_data").set_state(data.decode("utf-8"))

            return data
        except IndexError as e:
            logger.warning(
                "Index error when handling remote data, probably wrong number of items in list. "
                "Nothing to worry about unless this happens a lot. "
                f"({e.__class__.__qualname__}: {e})"
            )
        except Exception as e:
            logger.exception(
                f"Exception handling remote data. ({e.__class__.__qualname__}: {e})"
            )

    async def local_mitm_handler(self, data):
        # logger.debug(f"JuiceboxMQTTHandler Function: {sys._getframe().f_code.co_name}")
        message = None
        try:
            logger.debug(f"Local: {data}")
            if "JuiceboxMITM_OSERROR" in str(data):
                message = await self.udp_mitm_oserror_message_parse(data)
            elif ":DBG," in str(data):
                message = await self.debug_message_parse(data)
            else:
                message = await self.basic_message_parse(data)
            if message:
                await self.basic_message_publish(message)
            return data
        except IndexError as e:
            logger.warning(
                "Index error when handling local data, probably wrong number of items in list"
                "Nothing to worry about unless this happens a lot. "
                f"({e.__class__.__qualname__}: {e})"
            )
        except Exception as e:
            logger.exception(
                f"Exception handling local data. ({e.__class__.__qualname__}: {e})"
            )
