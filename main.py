"""
天依美食雷达 - AstrBot插件
配合Tasker定位 + 高德地图API，在群里帮人找好吃的
"""
import aiohttp
import random
import time
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.message_components import *


class TianyiFoodRadar(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.cfg = config or {}
        self.amap_key = self.cfg.get("amap_key", "")
        self.server_url = self.cfg.get("location_server", "http://localhost:8899")
        self.server_secret = self.cfg.get("location_secret", "tianyi_food_radar_2024")
        self.radius = int(self.cfg.get("search_radius", 1500))
        self.top_n = int(self.cfg.get("result_count", 5))

    # ---------- 抓位置 ----------
    async def _get_location(self):
        """去定位服务器拿最新位置"""
        url = f"{self.server_url}/api/location/latest?secret={self.server_secret}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    j = await r.json()
            if j.get("ok"):
                return j["data"]
        except Exception:
            pass
        return None

    # ---------- 调高德 ----------
    async def _search_food(self, lat, lng):
        """高德周边搜索，关键词美食"""
        url = "https://restapi.amap.com/v3/place/around"
        params = {
            "key": self.amap_key,
            "location": f"{lng},{lat}",
            "keywords": "美食|餐厅|小吃|火锅|烧烤|奶茶|甜品",
            "radius": self.radius,
            "offset": min(self.top_n + 5, 25),
            "page": 1,
            "extensions": "all",
            "sortrule": "weight",
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    j = await r.json()
            if j.get("status") == "1" and j.get("pois"):
                return j["pois"]
        except Exception:
            pass
        return []

    # ---------- 洛天依式回复生成 ----------
    def _make_reply(self, pois, lat, lng):
        """把高德返回的店列表，弄成天依会说的话"""
        if not pois:
            return random.choice([
                "唔…这附近好像没啥好吃的诶",
                "搜不到诶 你是不是在荒郊野外啊",
                "雷达没扫到…换个大点范围试试？",
            ])

        # 挑几个评分高的
        with_rating = [p for p in pois if p.get("biz_ext", {}).get("rating")]
        with_rating.sort(key=lambda p: float(p.get("biz_ext", {}).get("rating", 0)), reverse=True)

        if not with_rating:
            with_rating = pois[:self.top_n]

        picks = with_rating[:self.top_n]

        lines = []
        # 开头
        openings = [
            "诶~ 雷达扫到好吃的了！",
            "唔 附近有这几家… 看看？",
            "找到啦找到啦 你看这些行不~",
            "嘿嘿 搜到几家不错的捏",
        ]
        lines.append(random.choice(openings))

        for i, p in enumerate(picks, 1):
            name = p.get("name", "?")
            addr = p.get("address", "")
            dist = p.get("distance", "?")
            biz = p.get("biz_ext", {})
            rating = biz.get("rating", "")
            cost = biz.get("cost", "")
            ptype = p.get("type", "").split(";")

            # 类型提取（简短点）
            type_str = ""
            food_tags = {"中餐厅", "火锅", "烧烤", "奶茶", "甜品", "小吃", "面馆", "西餐", "日料", "韩餐", "川菜", "粤菜", "快餐", "咖啡"}
            for t in ptype:
                for ft in food_tags:
                    if ft in t:
                        type_str = ft
                        break
                if type_str:
                    break

            # 拼两行：第一行名字+评分+距离，第二行地址+人均
            line1 = [f"{i}.{name}"]
            if type_str:
                line1.append(f"[{type_str}]")
            if rating and rating != "0":
                line1.append(f"⭐{rating}")
            if dist and dist != "?":
                m = int(dist)
                if m < 1000:
                    line1.append(f"{m}m")
                else:
                    line1.append(f"{m / 1000:.1f}km")
            lines.append("  ".join(line1))

            line2_parts = []
            if cost and cost != "0":
                line2_parts.append(f"人均¥{cost}")
            if addr:
                line2_parts.append(addr[:15])
            if line2_parts:
                lines.append("   " + "  ".join(line2_parts))

            # 高德导航链接
            location = p.get("location", "")
            if location:
                lines.append(f"   https://uri.amap.com/navigation?to={location},{name}")

            lines.append("")  # 空行隔开

        # 收尾
        endings = [
            "要去哪家呀 天依也想去…",
            "选好了告诉我哦~",
            "别光看不动啊 饿了饿了",
        ]
        lines.append(random.choice(endings))

        return "\n".join(lines)

    # ---------- 地理编码 ----------
    async def _geocode(self, address: str):
        """把地址文字转成经纬度"""
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {"key": self.amap_key, "address": address}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    j = await r.json()
            if j.get("status") == "1" and j.get("geocodes"):
                loc = j["geocodes"][0]["location"]
                lng, lat = loc.split(",")
                return float(lat), float(lng)
        except Exception:
            pass
        return None, None

    # ---------- 指令：附近吃的 ----------
    @filter.command("/找吃的", alias={"/附近吃的", "/吃啥", "/美食", "/推荐吃的", "/food", "找吃的", "附近吃的", "吃啥"})
    async def cmd_food(self, event: AstrMessageEvent, location: str = ""):
        """按需拉位置->高德搜店->天依给你推荐~
        
        说"找吃的"用手机定位，"找吃的 徐家汇"搜指定地点

        Args:
            location(string): 可选，搜哪个地方，比如"徐家汇"、"静安寺"
        """
        if not self.amap_key:
            yield event.plain_result("唔 老大还没配高德地图的key… 帮我@一下依一壹1")
            return

        lat, lng = None, None
        if location:
            lat, lng = await self._geocode(location)
            if lat is None:
                yield event.plain_result(f"唔…找不到{location}在哪诶")
                return
        else:
            loc = await self._get_location()
            if not loc:
                yield event.plain_result("诶 拿不到你的位置诶… 试试说「找吃的 徐汇」加上地点？")
                return
            lat = loc.get("lat")
            lng = loc.get("lng")

        pois = await self._search_food(lat, lng)
        reply = self._make_reply(pois, lat, lng)
        yield event.plain_result(reply)

    # ---------- 指令：具体想吃什么 ----------
    @filter.command("/想吃")
    async def cmd_craving(self, event: AstrMessageEvent, keyword: str = "", location: str = ""):
        """搜特定类型的店~ 可指定地点

        比如"想吃火锅"、"想吃奶茶 静安寺"

        Args:
            keyword(string): 想吃啥
            location(string): 可选，在哪个地方搜
        """
        if not keyword:
            yield event.plain_result("想吃啥你倒是说呀…")
            return

        if not self.amap_key:
            yield event.plain_result("唔 老大还没配高德地图的key… 帮我@一下依一壹1")
            return

        lat, lng = None, None
        if location:
            lat, lng = await self._geocode(location)
            if lat is None:
                yield event.plain_result(f"唔…找不到{location}在哪诶")
                return
        else:
            loc = await self._get_location()
            if not loc:
                yield event.plain_result("诶 拿不到位置…试试「想吃火锅 徐汇」加上地点？")
                return
            lat = loc.get("lat")
            lng = loc.get("lng")

        # 直接搜关键词
        url = "https://restapi.amap.com/v3/place/around"
        params = {
            "key": self.amap_key,
            "location": f"{lng},{lat}",
            "keywords": keyword,
            "radius": self.radius,
            "offset": min(self.top_n + 5, 20),
            "page": 1,
            "extensions": "all",
            "sortrule": "weight",
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    j = await r.json()
            pois = j.get("pois", []) if j.get("status") == "1" else []
        except Exception:
            pois = []

        if not pois:
            yield event.plain_result(f"附近好像没有{keyword}诶… 换一个试试？")
            return

        picks = pois[:self.top_n]
        lines = [f"诶 搜到{keyword}的了~"]

        for i, p in enumerate(picks, 1):
            name = p.get("name", "?")
            addr = p.get("address", "")
            dist = p.get("distance", "?")
            rating = p.get("biz_ext", {}).get("rating", "")
            cost = p.get("biz_ext", {}).get("cost", "")

            line1 = [f"{i}.{name}"]
            if rating and rating != "0":
                line1.append(f"⭐{rating}")
            if dist and dist != "?":
                m = int(dist)
                line1.append(f"{m}m" if m < 1000 else f"{m / 1000:.1f}km")
            lines.append("  ".join(line1))

            line2_parts = []
            if cost and cost != "0":
                line2_parts.append(f"人均¥{cost}")
            if addr:
                line2_parts.append(addr[:15])
            if line2_parts:
                lines.append("   " + "  ".join(line2_parts))
            location = p.get("location", "")
            if location:
                lines.append(f"   https://uri.amap.com/navigation?to={location},{name}")
            lines.append("")

        lines.append("想去哪家 跟我说~")
        yield event.plain_result("\n".join(lines))

    # ---------- 看看定位在不在 ----------
    @filter.command("/我在哪", alias={"/whereami", "/我在哪里", "我在哪", "whereami"})
    async def cmd_where(self, event: AstrMessageEvent):
        """看看上次上报的位置"""
        loc = await self._get_location()
        if not loc:
            yield event.plain_result("不知道诶… 手机没传位置上来")
            return

        lat, lng = loc["lat"], loc["lng"]
        # 逆地理编码拿个地址
        url = "https://restapi.amap.com/v3/geocode/regeo"
        params = {
            "key": self.amap_key,
            "location": f"{lng},{lat}",
            "extensions": "base",
        }
        addr = ""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    j = await r.json()
            addr = j.get("regeocode", {}).get("formatted_address", "")
        except Exception:
            pass

        ago = ""
        if loc.get("timestamp"):
            sec = int(time.time() - loc["timestamp"])
            if sec < 60:
                ago = "刚刚"
            elif sec < 3600:
                ago = f"{sec // 60}分钟前"
            else:
                ago = f"{sec // 3600}小时前"

        yield event.plain_result(f"你在{addr}附近~ {ago}上报的")

    # ---------- 自然语言兜底 ----------
    @filter.regex(r"^/?(附近|周边|这附近|周围|帮我|给我).*(推荐|找|搜|看看|好吃的|吃啥|吃的|美食)")
    async def on_food_mention(self, event: AstrMessageEvent):
        """不需要精确命令，聊到吃的就能触发"""
        if not self.amap_key:
            return  # 没配置key就装死
        loc = await self._get_location()
        if not loc:
            yield event.plain_result("诶 拿不到你的位置诶… 手机开了定位没呀")
            return
        pois = await self._search_food(loc["lat"], loc["lng"])
        yield event.plain_result(self._make_reply(pois, loc["lat"], loc["lng"]))

    @filter.regex(r"^/?想吃(.+)")
    async def on_craving_natural(self, event: AstrMessageEvent):
        """想吃xxx 的自然语言版"""
        import re
        msg = event.message_str
        m = re.match(r"^想吃(.+)", msg)
        if not m:
            return
        keyword = m.group(1).strip()
        if not keyword:
            yield event.plain_result("想吃啥你倒是说呀…")
            return

        if not self.amap_key:
            return
        loc = await self._get_location()
        if not loc:
            yield event.plain_result("诶 拿不到你的位置诶…")
            return

        url = "https://restapi.amap.com/v3/place/around"
        params = {
            "key": self.amap_key,
            "location": f"{loc['lng']},{loc['lat']}",
            "keywords": keyword,
            "radius": self.radius,
            "offset": min(self.top_n + 5, 20),
            "page": 1,
            "extensions": "all",
            "sortrule": "weight",
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    j = await r.json()
            pois = j.get("pois", []) if j.get("status") == "1" else []
        except Exception:
            pois = []

        if not pois:
            yield event.plain_result(f"附近好像没有{keyword}诶… 换一个试试？")
            return

        picks = pois[:self.top_n]
        lines = [f"诶 搜到{keyword}的了~"]
        for i, p in enumerate(picks, 1):
            name = p.get("name", "?")
            addr = p.get("address", "")
            dist = p.get("distance", "?")
            rating = p.get("biz_ext", {}).get("rating", "")
            cost = p.get("biz_ext", {}).get("cost", "")
            line1 = [f"{i}.{name}"]
            if rating and rating != "0":
                line1.append(f"⭐{rating}")
            if dist and dist != "?":
                m = int(dist)
                line1.append(f"{m}m" if m < 1000 else f"{m / 1000:.1f}km")
            lines.append("  ".join(line1))
            line2_parts = []
            if cost and cost != "0":
                line2_parts.append(f"人均¥{cost}")
            if addr:
                line2_parts.append(addr[:15])
            if line2_parts:
                lines.append("   " + "  ".join(line2_parts))
            location = p.get("location", "")
            if location:
                lines.append(f"   https://uri.amap.com/navigation?to={location},{name}")
            lines.append("")
        lines.append("想去哪家 跟我说~")
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        pass
