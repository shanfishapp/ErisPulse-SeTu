from ErisPulse import sdk
import aiohttp
import asyncio

class Main:
    def __init__(self):
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = sdk.adapter
        self._register_handlers()
    
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
                self.logger.warning(f"平台不支持图片发送")
                return

            image_url = await self._fetch_image_url()
            if not image_url:
                self.logger.warning("图片API请求失败")
                return
            
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
            raise ValueError("无法获取消息来源平台")
            
        adapter = getattr(self.sdk.adapter, adapter_name)
        return adapter.Send.To("user" if detail_type == "private" else "group", datail_id)

    async def _fetch_image_url(self):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.lolicon.app/setu/v2") as resp:
                if resp.status != 200:
                    return None
                json_data = await resp.json()
                self.logger.info(json_data['data'][0]['urls']['original'])
                return json_data['data'][0]['urls']['original']

    async def _stream_download(self, url, chunk_size=256 * 1024):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"下载失败，状态码: {response.status}")
                async for chunk in response.content.iter_chunked(chunk_size):
                    yield chunk
                    await asyncio.sleep(0.01)
    
    async def _download_full_image(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"下载失败，状态码: {response.status}")
                return await response.read()
                