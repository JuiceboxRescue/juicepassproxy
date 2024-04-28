import asyncio
import logging

from juicebox_telnet import JuiceboxTelnet

logger = logging.getLogger(__name__)


class JuiceboxUDPCUpdater:
    def __init__(
        self,
        juicebox_host,
        udpc_host,
        udpc_port=8047,
        telnet_timeout=None,
        loglevel=None,
    ):
        # logger.debug(f"JuiceboxUDPCUpdater Function: {sys._getframe().f_code.co_name}")
        if loglevel is not None:
            logger.setLevel(loglevel)
        self.juicebox_host = juicebox_host
        self.udpc_host = udpc_host
        self.udpc_port = udpc_port
        self.interval = 30
        self.run_event = True
        self.telnet_timeout = telnet_timeout
        self._telnet = None

    async def start(self):
        # logger.debug(f"JuiceboxUDPCUpdater Function: {sys._getframe().f_code.co_name}")
        logger.info("Starting JuiceboxUDPCUpdater")
        try:
            await self._connect_to_juicebox_telnet()
            await self._update_juicebox_udpc()
        # except Exception as e:
        #    logger.error(f"Error during Juicebox UDPC update: ({e.__class__.__qualname__}: {e})")
        finally:
            await self._close_telnet()

    async def _connect_to_juicebox_telnet(self):
        # logger.debug(f"JuiceboxUDPCUpdater Function: {sys._getframe().f_code.co_name}")
        logger.info("Connecting to Juicebox Telnet")
        self._telnet = JuiceboxTelnet(
            self.juicebox_host,
            loglevel=logger.getEffectiveLevel(),
            timeout=self.telnet_timeout,
        )
        await self._telnet.open()
        logger.info("Connected to Juicebox Telnet")

    async def _update_juicebox_udpc(self):
        # logger.debug(f"JuiceboxUDPCUpdater Function: {sys._getframe().f_code.co_name}")
        # logger.info("Updating Juicebox UDPC")
        while self.run_event:
            interval = self.interval
            try:
                logger.info("JuiceboxUDPCUpdater Check Starting")
                connections = await self._telnet.list()
                update_required = True
                udpc_streams_to_close = {}  # Key = Connection id, Value = list id
                udpc_stream_to_update = 0

                # logger.debug(f"connections: {connections}")

                for i, connection in enumerate(connections):
                    if connection["type"] == "UDPC":
                        udpc_streams_to_close.update({int(connection["id"]): i})
                        if self.udpc_host not in connection["dest"]:
                            udpc_stream_to_update = int(connection["id"])
                # logger.debug(f"udpc_streams_to_close: {udpc_streams_to_close}")
                if udpc_stream_to_update == 0 and len(udpc_streams_to_close) > 0:
                    udpc_stream_to_update = int(max(udpc_streams_to_close, key=int))
                logger.debug(f"Active UDPC Stream: {udpc_stream_to_update}")

                for stream in list(udpc_streams_to_close):
                    if stream < udpc_stream_to_update:
                        udpc_streams_to_close.pop(stream, None)

                if len(udpc_streams_to_close) == 0:
                    logger.info("UDPC IP not found, updating")
                elif (
                    self.udpc_host
                    not in connections[udpc_streams_to_close[udpc_stream_to_update]][
                        "dest"
                    ]
                ):
                    logger.info("UDPC IP incorrect, updating")
                elif len(udpc_streams_to_close) == 1:
                    logger.info("UDPC IP correct")
                    update_required = False

                if update_required:
                    for id in udpc_streams_to_close:
                        logger.debug(f"Closing UDPC stream: {id}")
                        await self._telnet.stream_close(id)
                    await self._telnet.write_udpc(self.udpc_host, self.udpc_port)
                    await self._telnet.save()
                    logger.info("UDPC IP Saved")
            except ConnectionResetError as e:
                logger.warning(
                    "Telnet connection to JuiceBox lost. "
                    "Nothing to worry about unless this happens a lot. "
                    f"({e.__class__.__qualname__}: {e})"
                )
                interval = 3
            except TimeoutError as e:
                logger.warning(
                    "Telnet connection to JuiceBox has timed out"
                    "Nothing to worry about unless this happens a lot. "
                    f"({e.__class__.__qualname__}: {e})"
                )
                interval = 3
            except OSError as e:
                logger.warning(
                    "Could not route Telnet connection to JuiceBox"
                    "Nothing to worry about unless this happens a lot. "
                    f"({e.__class__.__qualname__}: {e})"
                )
                interval = 3
            # except Exception as e:
            #    logger.exception(f"Error in JuiceboxUDPCUpdater: ({e.__class__.__qualname__}: {e})")
            await asyncio.sleep(interval)

    async def _close_telnet(self):
        # logger.debug(f"JuiceboxUDPCUpdater Function: {sys._getframe().f_code.co_name}")
        if self._telnet:
            await self._telnet.close()
