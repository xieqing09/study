#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音图片爬虫 - 基于Crawl4AI
专门用于爬取抖音平台的图片内容
注意：请遵守抖音平台的使用条款和相关法律法规
"""

import asyncio
import json
import os
import requests
import time
import random
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from typing import List, Dict, Optional

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from linkrush import extract_links_from_file

# Selenium相关导入
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    print("警告: Selenium未安装，部分功能将不可用。请运行: pip install selenium")
    SELENIUM_AVAILABLE = False

class DouyinImageCrawler:
    def __init__(self, download_dir: str = "douyin_images"):
        """
        初始化抖音图片爬虫
        
        Args:
            download_dir: 图片下载目录
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        
        # 抖音相关的User-Agent
        self.user_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ]
        
    def _get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(self.user_agents)
    
    def _add_random_delay(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """添加随机延迟，避免被检测"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def _validate_and_clean_url(self, url: str) -> str:
        """
        验证和清理URL，确保格式正确
        
        Args:
            url: 原始URL
            
        Returns:
            清理后的有效URL
            
        Raises:
            ValueError: 如果URL无法修复为有效格式
        """
        if not url or not isinstance(url, str):
            raise ValueError("URL不能为空且必须是字符串")
        
        # 去除首尾空白字符和特殊字符
        url = url.strip().strip('\'"`')
        
        # 如果URL为空
        if not url:
            raise ValueError("URL不能为空")
        
        # 尝试从文本中提取URL（如果输入包含其他文本）
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        url_matches = re.findall(url_pattern, url)
        if url_matches:
            url = url_matches[0]
        
        # 如果没有协议，添加https://
        if not url.startswith(('http://', 'https://')):
            # 检查是否是抖音相关域名
            if 'douyin.com' in url or 'v.douyin.com' in url:
                url = 'https://' + url
            else:
                url = 'https://' + url
        
        # 使用urlparse验证URL格式
        try:
            parsed = urlparse(url)
            
            # 检查是否有有效的域名
            if not parsed.netloc:
                raise ValueError(f"URL缺少有效域名: {url}")
            
            # 重新构建URL，确保格式正确
            cleaned_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                cleaned_url += f"?{parsed.query}"
            if parsed.fragment:
                cleaned_url += f"#{parsed.fragment}"
            
            print(f"URL验证通过: {url} -> {cleaned_url}")
            return cleaned_url
            
        except Exception as e:
            # 如果标准验证失败，尝试提取URL
            try:
                return self._extract_valid_url_from_text(url)
            except:
                raise ValueError(f"URL格式无效: {url}, 错误: {str(e)}")
    
    def _extract_valid_url_from_text(self, text: str) -> str:
        """
        从文本中提取有效的URL
        
        Args:
            text: 包含URL的文本
            
        Returns:
            提取出的有效URL
        """
        import re
        
        print(f"正在从文本中提取URL: {text}")
        
        # 专门针对抖音URL的正则表达式模式
        douyin_patterns = [
            r'https?://v\.douyin\.com/[a-zA-Z0-9]+/?',  # 抖音短链接
            r'https?://www\.douyin\.com/[^\s<>"{}|\\^`\[\]]*',  # 抖音完整链接
            r'https?://[^\s<>"{}|\\^`\[\]]*douyin[^\s<>"{}|\\^`\[\]]*',  # 包含douyin的链接
        ]
        
        # 通用URL正则表达式模式
        general_patterns = [
            r'https?://[^\s<>"{}|\\^`\[\]]+',  # 标准HTTP/HTTPS URL
            r'www\.[^\s<>"{}|\\^`\[\]]+',      # www开头的URL
        ]
        
        # 首先尝试抖音专用模式
        for pattern in douyin_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 清理URL末尾的特殊字符
                cleaned_match = re.sub(r'[`\'"]+$', '', match.strip())
                try:
                    validated_url = self._validate_and_clean_url(cleaned_match)
                    print(f"找到抖音URL: {cleaned_match} -> {validated_url}")
                    return validated_url
                except ValueError as e:
                    print(f"抖音URL验证失败: {cleaned_match}, 错误: {e}")
                    continue
        
        # 如果没有找到抖音URL，尝试通用模式
        for pattern in general_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 清理URL末尾的特殊字符
                cleaned_match = re.sub(r'[`\'"]+$', '', match.strip())
                try:
                    validated_url = self._validate_and_clean_url(cleaned_match)
                    print(f"找到通用URL: {cleaned_match} -> {validated_url}")
                    return validated_url
                except ValueError as e:
                    print(f"通用URL验证失败: {cleaned_match}, 错误: {e}")
                    continue
        
        # 如果没有找到有效URL，抛出异常
        raise ValueError(f"无法从文本中提取有效URL: {text}")
    
    async def crawl_douyin_user_images(self, user_url: str, max_images: int = 50, 
                                     save_metadata: bool = True, use_selenium: bool = True) -> Dict:
        """
        爬取抖音用户主页的图片
        
        Args:
            user_url: 抖音用户主页URL
            max_images: 最大爬取图片数量
            save_metadata: 是否保存元数据
            use_selenium: 是否使用Selenium获取真实图片URL
            
        Returns:
            包含爬取结果的字典
        """
        print(f"开始爬取抖音用户: {user_url}")
        
        results = {
            "user_url": user_url,
            "total_images": 0,
            "downloaded_images": 0,
            "failed_downloads": 0,
            "images_metadata": [],
            "method_used": "selenium" if use_selenium and SELENIUM_AVAILABLE else "crawl4ai"
        }
        
        # 优先使用Selenium获取真实图片URL
        if use_selenium and SELENIUM_AVAILABLE:
            print("使用Selenium方法获取图片...")
            try:
                # 使用Selenium获取真实图片URL
                selenium_urls = self.get_real_image_urls_with_selenium(user_url, max_images)
                
                if selenium_urls:
                    print(f"Selenium获取到 {len(selenium_urls)} 个图片URL")
                    results["total_images"] = len(selenium_urls)
                    
                    # 下载Selenium获取的图片
                    for i, img_url in enumerate(selenium_urls, 1):
                        # 构造图片数据字典
                        img_data = {
                            'src': img_url,
                            'alt': f'douyin_image_{i}',
                            'width': 'unknown',
                            'height': 'unknown',
                            'score': 1.0
                        }
                        
                        success = await self._download_douyin_image(img_data, user_url, i)
                        if success:
                            results["downloaded_images"] += 1
                            if save_metadata:
                                results["images_metadata"].append(img_data)
                        else:
                            results["failed_downloads"] += 1
                        
                        # 添加延迟避免被封
                        if i % 3 == 0:  # 每3张图片后延迟
                            self._add_random_delay(2, 4)
                    
                    # 如果Selenium成功获取到图片，直接返回结果
                    if results["downloaded_images"] > 0:
                        print(f"Selenium方法成功下载 {results['downloaded_images']} 张图片")
                        if save_metadata and results["images_metadata"]:
                            metadata_file = self.download_dir / "douyin_metadata_selenium.json"
                            with open(metadata_file, 'w', encoding='utf-8') as f:
                                json.dump(results, f, ensure_ascii=False, indent=2)
                            print(f"元数据已保存到: {metadata_file}")
                        return results
                    
            except Exception as e:
                print(f"Selenium方法失败: {str(e)}，回退到Crawl4AI方法")
        
        # 回退到原有的Crawl4AI方法
        print("使用Crawl4AI方法获取图片...")
        results["method_used"] = "crawl4ai"
        
        # 配置浏览器 - 模拟移动端
        browser_config = BrowserConfig(
            headless=True,
            viewport_width=375,   # iPhone宽度
            viewport_height=812,  # iPhone高度
            user_agent=self._get_random_user_agent(),
            java_script_enabled=True,
            verbose=True
        )
        
        # 配置爬虫
        crawler_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            exclude_external_images=False,
            wait_for="() => document.querySelectorAll('img').length > 5",  # 等待图片加载
            js_code="""
                // 模拟滚动加载更多内容
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(resolve => setTimeout(resolve, 2000));
                window.scrollTo(0, document.body.scrollHeight);
            """,
            screenshot=False
        )
        
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=user_url, config=crawler_config)
                
                if not result.success:
                    print(f"爬取失败: {result.error_message}")
                    return results
                
                # 获取图片列表
                images = result.media.get("images", [])
                results["total_images"] = len(images)
                
                print(f"发现 {len(images)} 张图片")
                
                # 过滤抖音相关图片（排除UI元素）
                douyin_images = self._filter_douyin_images(images)
                print(f"过滤后剩余 {len(douyin_images)} 张抖音内容图片")
                
                # 限制下载数量
                if max_images > 0:
                    douyin_images = douyin_images[:max_images]
                    print(f"限制下载数量为 {len(douyin_images)} 张")
                
                # 下载图片
                for i, img in enumerate(douyin_images, 1):
                    success = await self._download_douyin_image(img, user_url, i)
                    if success:
                        results["downloaded_images"] += 1
                        if save_metadata:
                            results["images_metadata"].append(img)
                    else:
                        results["failed_downloads"] += 1
                    
                    # 添加延迟避免被封
                    if i % 5 == 0:  # 每5张图片后延迟
                        self._add_random_delay(2, 5)
                
                # 保存元数据
                if save_metadata and results["images_metadata"]:
                    metadata_file = self.download_dir / "douyin_metadata.json"
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    print(f"元数据已保存到: {metadata_file}")
                
        except Exception as e:
            print(f"爬取过程中出现错误: {str(e)}")
            
        return results
    
    def _filter_douyin_images(self, images: List[Dict]) -> List[Dict]:
        """
        过滤抖音图片，排除UI元素和无关图片
        
        Args:
            images: 原始图片列表
            
        Returns:
            过滤后的图片列表
        """
        filtered_images = []
        
        for img in images:
            src = img.get('src', '')
            alt = img.get('alt', '').lower()
            
            # 放宽排除条件
            if any([
                # 只排除极小尺寸图片
                (img.get('width') or 0) < 50 or (img.get('height') or 0) < 50,
                # 只排除明显的UI元素
                'favicon' in src.lower() or 'sprite' in src.lower(),
                # 排除base64图片（通常是小图标）
                src.startswith('data:image'),
                # 排除空src
                not src or src == '#'
            ]):
                continue
            
            # 包含更多图片类型
            if any([
                # 抖音视频封面
                'cover' in src.lower(),
                # 用户上传的图片
                'upload' in src.lower(),
                # 降低分辨率要求
                (img.get('width') or 0) > 100 and (img.get('height') or 0) > 100,
                # 有意义的alt文本
                len(alt) > 3,
                # 包含常见图片格式
                any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])
            ]):
                filtered_images.append(img)
            elif img.get('score', 0) > 0.1:  # 降低评分要求
                filtered_images.append(img)
            else:
                # 如果都不满足，也尝试包含（更宽松策略）
                filtered_images.append(img)
        
        return filtered_images
    
    async def _download_douyin_image(self, img_data: Dict, base_url: str, index: int) -> bool:
        """
        下载抖音图片
        
        Args:
            img_data: 图片数据字典
            base_url: 基础URL
            index: 图片索引
            
        Returns:
            下载是否成功
        """
        try:
            img_url = img_data.get('src', '')
            if not img_url:
                print(f"图片 {index}: 缺少src属性")
                return False
            
            # 处理抖音图片URL
            img_url = self._process_douyin_image_url(img_url, base_url)
            
            # 获取文件扩展名
            parsed_url = urlparse(img_url)
            file_ext = os.path.splitext(parsed_url.path)[1]
            if not file_ext or file_ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                file_ext = '.jpg'  # 默认扩展名
            
            # 生成文件名
            alt_text = img_data.get('alt', '').strip()
            if alt_text:
                safe_alt = "".join(c for c in alt_text if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_alt = safe_alt[:30]  # 限制长度
                filename = f"douyin_{index:03d}_{safe_alt}{file_ext}"
            else:
                filename = f"douyin_{index:03d}_image{file_ext}"
            
            file_path = self.download_dir / filename
            
            # 下载图片 - 使用抖音兼容的请求头
            headers = {
                'User-Agent': self._get_random_user_agent(),
                'Referer': 'https://www.douyin.com/',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site'
            }
            
            response = requests.get(img_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # 检查内容类型
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                print(f"图片 {index}: 不是有效的图片文件 (Content-Type: {content_type})")
                return False
            
            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content)
            print(f"图片 {index}: 下载成功 - {filename} ({file_size} bytes)")
            print(f"  URL: {img_url}")
            print(f"  尺寸: {img_data.get('width', 'N/A')}x{img_data.get('height', 'N/A')}")
            print(f"  评分: {img_data.get('score', 'N/A')}")
            print()
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"图片 {index}: 下载失败 - 网络错误: {str(e)}")
            return False
        except Exception as e:
            print(f"图片 {index}: 下载失败 - {str(e)}")
            return False
    
    def _process_douyin_image_url(self, img_url: str, base_url: str) -> str:
        """
        处理抖音图片URL，确保可以正常访问
        
        Args:
            img_url: 原始图片URL
            base_url: 基础URL
            
        Returns:
            处理后的图片URL
        """
        # 处理相对URL
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = urljoin(base_url, img_url)
        elif not img_url.startswith(('http://', 'https://')):
            img_url = urljoin(base_url, img_url)
        
        # 处理抖音CDN URL参数
        if 'douyin.com' in img_url or 'bytedance.com' in img_url:
            # 移除可能导致403的参数
            parsed = urlparse(img_url)
            query_params = parse_qs(parsed.query)
            
            # 保留必要参数，移除签名相关参数
            keep_params = {}
            for key, value in query_params.items():
                if key.lower() not in ['x-expires', 'x-signature', 'x-tt-token']:
                    keep_params[key] = value
            
            # 重构URL
            if keep_params:
                query_string = '&'.join([f"{k}={'&'.join(v)}" for k, v in keep_params.items()])
                img_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_string}"
            else:
                img_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        return img_url
    
    def get_real_image_urls_with_selenium(self, page_url: str, max_images: int = 20) -> List[str]:
        """
        使用Selenium获取真实的图片URL
        
        Args:
            page_url: 页面URL
            max_images: 最大获取图片数量
            
        Returns:
            图片URL列表
        """
        if not SELENIUM_AVAILABLE:
            print("错误: Selenium未安装，无法使用此功能")
            return []
        
        # 验证和清理URL
        try:
            validated_url = self._validate_and_clean_url(page_url)
            print(f"使用Selenium获取真实图片URL: {validated_url}")
        except ValueError as e:
            print(f"URL验证失败: {e}")
            # 尝试从文本中提取有效URL
            try:
                validated_url = self._extract_valid_url_from_text(page_url)
                print(f"从文本中提取到有效URL: {validated_url}")
            except ValueError as extract_error:
                print(f"无法提取有效URL: {extract_error}")
                return []
        
        # 配置Chrome选项
        chrome_options = Options()
        chrome_options.binary_location = os.path.join(os.getcwd(), 'GoogleChromePortable', 'App', 'Chrome-bin', 'chrome.exe')
        chrome_options.add_argument('--headless')  # 无头模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')  # 禁用图片加载以提高速度
        chrome_options.add_argument('--window-size=375,812')  # 设置窗口大小模拟移动端
        
        # 设置用户代理
        user_agent = self._get_random_user_agent()
        chrome_options.add_argument(f'--user-agent={user_agent}')
        
        # 添加移动端模拟 - 简化配置
        mobile_emulation = {
            "deviceMetrics": {"width": 375, "height": 812, "pixelRatio": 2.0},
            "userAgent": user_agent
        }
        chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
        
        driver = None
        image_urls = []
        
        try:
            # 设置ChromeDriver路径 - 修复路径问题
            chromedriver_path = os.path.join(os.getcwd(), 'chromedriver', 'chromedriver-win64 (1)', 'chromedriver-win64', 'chromedriver.exe')
            
            # 创建WebDriver实例
            if os.path.exists(chromedriver_path):
                print(f"使用本地ChromeDriver: {chromedriver_path}")
                service = Service(chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                print(f"本地ChromeDriver不存在: {chromedriver_path}")
                print("尝试使用系统PATH中的chromedriver...")
                try:
                    # 如果本地路径不存在，使用系统PATH中的chromedriver
                    driver = webdriver.Chrome(options=chrome_options)
                except Exception as path_error:
                    print(f"系统PATH中也找不到ChromeDriver: {str(path_error)}")
                    # 尝试使用Selenium Manager自动下载
                    print("尝试使用Selenium Manager自动管理ChromeDriver...")
                    from selenium.webdriver.chrome.service import Service as ChromeService
                    service = ChromeService()
                    driver = webdriver.Chrome(service=service, options=chrome_options)
            
            driver.set_page_load_timeout(30)
            
            # 访问页面 - 使用验证后的URL
            driver.get(validated_url)
            
            # 等待页面加载
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "img"))
            )
            
            # 模拟滚动加载更多内容
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # 等待新内容加载
                try:
                    WebDriverWait(driver, 5).until(
                        lambda d: len(d.find_elements(By.TAG_NAME, "img")) > i * 5
                    )
                except TimeoutException:
                    pass
            
            # 获取所有图片元素
            img_elements = driver.find_elements(By.TAG_NAME, "img")
            print(f"找到 {len(img_elements)} 个图片元素")
            
            # 提取图片URL
            for img in img_elements:
                try:
                    # 获取src属性
                    src = img.get_attribute('src')
                    if not src:
                        # 尝试获取data-src属性（懒加载）
                        src = img.get_attribute('data-src')
                    if not src:
                        # 尝试获取data-original属性
                        src = img.get_attribute('data-original')
                    
                    if src and self._is_valid_douyin_image(src, img):
                        # 处理URL
                        processed_url = self._process_douyin_image_url(src, page_url)
                        if processed_url not in image_urls:
                            image_urls.append(processed_url)
                            print(f"获取到图片URL: {processed_url}")
                            
                            if len(image_urls) >= max_images:
                                break
                                
                except Exception as e:
                    print(f"处理图片元素时出错: {str(e)}")
                    continue
            
            print(f"成功获取 {len(image_urls)} 个有效图片URL")
            
        except TimeoutException:
            print("页面加载超时")
        except Exception as e:
            print(f"Selenium获取图片URL时出错: {str(e)}")
        finally:
            if driver:
                driver.quit()
        
        return image_urls
    
    def _is_valid_douyin_image(self, src: str, img_element) -> bool:
        """
        判断是否为有效的抖音图片
        
        Args:
            src: 图片URL
            img_element: 图片元素
            
        Returns:
            是否为有效图片
        """
        if not src or src.startswith('data:image'):
            return False
        
        # 排除明显的UI元素
        if any(keyword in src.lower() for keyword in ['favicon', 'sprite', 'icon', 'logo']):
            return False
        
        # 检查图片尺寸
        try:
            width = img_element.get_attribute('width')
            height = img_element.get_attribute('height')
            
            if width and height:
                w, h = int(width), int(height)
                if w < 100 or h < 100:  # 排除过小的图片
                    return False
        except (ValueError, TypeError):
            pass
        
        # 检查是否包含抖音相关域名或路径
        douyin_indicators = [
            'douyinpic.com', 'bytedance.com', 'douyin.com',
            'cover', 'upload', 'avatar', 'video'
        ]
        
        return any(indicator in src.lower() for indicator in douyin_indicators)
    
    async def crawl_douyin_video_images(self, video_url: str, save_metadata: bool = True) -> Dict:
        """
        爬取单个抖音视频的图片（封面等）
        
        Args:
            video_url: 抖音视频URL
            save_metadata: 是否保存元数据
            
        Returns:
            包含爬取结果的字典
        """
        print(f"开始爬取抖音视频: {video_url}")
        
        browser_config = BrowserConfig(
            headless=True,
            viewport_width=375,
            viewport_height=812,
            user_agent=self._get_random_user_agent(),
            java_script_enabled=True
        )
        
        crawler_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            exclude_external_images=False,
            wait_for="() => document.querySelector('video') !== null",
            screenshot=False
        )
        
        results = {
            "video_url": video_url,
            "total_images": 0,
            "downloaded_images": 0,
            "failed_downloads": 0,
            "images_metadata": []
        }
        
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=video_url, config=crawler_config)
                
                if not result.success:
                    print(f"爬取失败: {result.error_message}")
                    return results
                
                images = result.media.get("images", [])
                results["total_images"] = len(images)
                
                # 过滤视频相关图片（降低要求）
                video_images = [img for img in images if 
                              (img.get('width') or 0) > 50 and (img.get('height') or 0) > 50]
                
                for i, img in enumerate(video_images, 1):
                    success = await self._download_douyin_image(img, video_url, i)
                    if success:
                        results["downloaded_images"] += 1
                        if save_metadata:
                            results["images_metadata"].append(img)
                    else:
                        results["failed_downloads"] += 1
                
                if save_metadata and results["images_metadata"]:
                    metadata_file = self.download_dir / f"video_metadata_{int(time.time())}.json"
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"爬取过程中出现错误: {str(e)}")
        
        return results
    
    def print_summary(self, results: Dict):
        """
        打印爬取结果摘要
        
        Args:
            results: 爬取结果字典
        """
        print("\n" + "="*60)
        print("抖音图片爬取结果摘要")
        print("="*60)
        print(f"目标URL: {results.get('user_url') or results.get('video_url')}")
        print(f"发现图片总数: {results['total_images']}")
        print(f"成功下载: {results['downloaded_images']}")
        print(f"下载失败: {results['failed_downloads']}")
        print(f"下载目录: {self.download_dir.absolute()}")
        print("="*60)

        print("="*60)

async def main():
    """
    主函数 - 抖音图片爬虫示例
    """
    print("抖音图片爬虫 - 基于Crawl4AI")

    print()
    
    # 创建抖音图片爬虫实例
    crawler = DouyinImageCrawler(download_dir="douyin_images")


    txt_path = r"C:\Users\qing\Desktop\爬虫_数据集\bug\lins.txt"  # 使用原始字符串避免转义问题

    # 从文件中提取链接
    user_urls = extract_links_from_file(txt_path)

    for user_url in user_urls:
        print(f"\n开始处理用户: {user_url}")

        
        results = await crawler.crawl_douyin_user_images(
            user_url=user_url,
            max_images=20,      # 限制下载数量
            save_metadata=True
        )
        
        crawler.print_summary(results)
    
    # 示例2: 爬取单个视频图片
    video_urls = [

    ]
    
    for video_url in video_urls:
        print(f"\n开始处理视频: {video_url}")
        
        results = await crawler.crawl_douyin_video_images(
            video_url=video_url,
            save_metadata=True
        )
        
        crawler.print_summary(results)
    


if __name__ == "__main__":
    # 运行爬虫
    asyncio.run(main())