from ErisPulse import sdk
import aiohttp
import asyncio
import os
from urllib.parse import unquote, urlparse

class Main:
    def __init__(self):
        self.sdk = sdk
        self.logger = sdk.logger
        self.adapter = sdk.adapter
        self._register_handlers()
        self.output_to_logger = None
        self.max_retries = 10
        self.temp_dir = "temp_images"
        
        # 创建临时目录
        os.makedirs(self.temp_dir, exist_ok=True)

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
            asyncio.create_task(self._process_image_request(data))

    async def _process_image_request(self, data):
        try:
            sender = await self._get_adapter_sender(data)
            if not hasattr(sender, 'Image'):
                await self._send_warning_text(data, "平台不支持图片发送")
                return
            if hasattr(sender, "Text"):
                msg_id_data = await sender.Text("收到了喵~正在为您准备图片喵~")
            else:
                self.logger.warning("平台不支持文本发送")
            retry_count = 0
            while retry_count < self.max_retries:
                temp_path = None
                try:
                    # 获取图片URL
                    image_url = await self._fetch_image_url(data)
                    if not image_url:
                        retry_count += 1
                        continue

                    # 获取原始文件名
                    file_name = self._get_filename_from_url(image_url)
                    temp_path = os.path.join(self.temp_dir, file_name)

                    # 下载文件
                    await self._download_to_file(image_url, temp_path)

                    # 读取文件内容
                    with open(temp_path, 'rb') as f:
                        image_data = f.read()

                    # 发送图片（不再使用stream=True）
                    adapter_name = data.get("self", {}).get("platform")
                    if hasattr(sender, "Edit"):
                        sender.Edit(msg_id_data['data']['messageInfo']['msgId'], "准备好了喵~尽情欣赏吧~")
                    else:
                        self.logger.warning("平台不支持编辑消息，将不会编辑消息")
                    await sender.Image(image_data)

                    self.logger.info(f"图片发送成功: {file_name}")
                    break

                except aiohttp.ClientError as e:
                    if "404" in str(e):
                        retry_count += 1
                        self.logger.warning(f"图片下载404错误，正在重试...({retry_count}/{self.max_retries})")
                        continue
                    await self._send_warning_text(data, f"图片下载失败: {str(e)}")
                    return
                except Exception as e:
                    await self._send_warning_text(data, f"图片处理失败: {str(e)}")
                    return
                finally:
                    # 清理临时文件
                    if temp_path and os.path.exists(temp_path):
                        await self._safe_delete(temp_path)

            if retry_count >= self.max_retries:
                await self._send_warning_text(data, "图片获取失败，已达到最大重试次数")

        except Exception as e:
            self.logger.error(f"图片处理失败: {str(e)}")
            await self._send_warning_text(data, f"图片处理失败: {str(e)}")

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
                    self.logger.warning(f"图片URL获取失败({resp.status})")
                    return None
                json_data = await resp.json()
                if json_data['error']:
                    self.logger.warning(f"图片API返回错误({json_data['error']})")
                    return None
                self.logger.info(json_data['data'][0]['urls']['original'])
                return json_data['data'][0]['urls']['original']

    def _get_filename_from_url(self, url):
        # 从URL中提取文件名
        parsed = urlparse(url)
        filename = unquote(os.path.basename(parsed.path))
        
        # 如果没有扩展名，添加默认的.jpg
        if not os.path.splitext(filename)[1]:
            filename += ".jpg"
            
        # 确保文件名安全
        return "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))

    async def _download_to_file(self, url, filepath):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 404:
                    raise aiohttp.ClientError("404 Not Found")
                elif response.status != 200:
                    raise aiohttp.ClientError(f"HTTP Error {response.status}")
                
                # 异步写入文件
                with open(filepath, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        f.write(chunk)

    async def _safe_delete(self, filepath):
        try:
            if os.path.exists(filepath):
                os.unlink(filepath)
                self.logger.debug(f"已删除临时文件: {filepath}")
        except Exception as e:
            self.logger.warning(f"删除临时文件失败: {filepath}, 错误: {str(e)}")