from ErisPulse import sdk
import aiohttp
import asyncio

class Main:
    def __init__(self):
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = sdk.adapter
        self._register_handlers()
        self.output_to_logger = None
    
    @staticmethod
    def should_eager_load() -> bool:
        return True

    def _register_handlers(self):
        self.adapter.on("message")(self._handle_message)
        self.logger.info("图片模块已加载")

    async def _handle_message(self, data):
        if not data.get("alt_message"):
            return
            
        text = data.get("alt_message", "").strip().lower()
        if text in ["/随机色图", "随机色图", "/色图", "色图"]:
            await self._process_image_request(data)

    async def _process_image_request(self, data):
        try:
            sender = await self._get_adapter_sender(data)
            if not hasattr(sender, 'Image'):
                await self._send_warning_text(data, "平台不支持图片发送")
                return

            image_url = await self._fetch_image_url(data)
            
            adapter_name = data.get("self", {}).get("platform")
            if adapter_name == "yunhu":
                await sender.Image(
                    self._stream_download(image_url),
                    stream=True
                )
            elif adapter_name == "onebot11":
                await sender.Image(image_url)
            else:
                image_bytes = await self._download_full_image(image_url)
                await sender.Image(image_bytes)

            self.logger.info("图片发送成功")

        except Exception as e:
            self.logger.error(f"图片处理失败: {str(e)}")

    async def _get_adapter_sender(self, data):
        detail_type = data.get("detail_type", "private")
        datail_id = data.get("user_id") if detail_type == "private" else data.get("group_id")
        adapter_name = data.get("self", {}).get("platform", None)
        
        self.logger.info(f"获取到消息来源: {adapter_name} {detail_type} {datail_id}")
        if not adapter_name:
            self.logger.warning("无法获取消息来源平台")
            
        adapter = getattr(self.sdk.adapter, adapter_name)
        return adapter.Send.To("user" if detail_type == "private" else "group", datail_id)

    async def _send_warning_text(self, data, text):
        sender = await self._get_adapter_sender(data)
        if hasattr(sender, "Text"):
            await sender.Text(text)
            return
        else:
            if not self.output_to_logger:
                self.logger.warning(f"平台不支持发送文字反馈，将输出到日志")
                self.output_to_logger = True
                self.logger.warning(text)
            else:
                self.logger.warning(text)
            return
                
    async def _fetch_image_url(self, data):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.lolicon.app/setu/v2") as resp:
                if resp.status != 200:
                    await self._send_warning_text(data, f"图片URL获取失败({resp.status})")
                    return
                json_data = await resp.json()
                if json_data['error']:
                     await self._send_warning_text(data, f"图片API返回错误({json_data['error']})")
                     return
                self.logger.info(json_data['data'][0]['urls']['original'])
                return json_data['data'][0]['urls']['original']

    async def _stream_download(self, url, chunk_size=256 * 1024):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"图片下载失败({response.status})")
                    return
                async for chunk in response.content.iter_chunked(chunk_size):
                    yield chunk
                    await asyncio.sleep(0.01)
    
    async def _download_full_image(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"图片下载失败({response.status})")
                    return
                return await response.read()