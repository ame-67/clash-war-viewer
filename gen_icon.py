# -*- coding: utf-8 -*-
"""生成程序图标 icon.ico: 蓝盾 + 金星"""
import math
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 盾牌外形
shield = [(128, 12), (210, 44), (210, 130), (128, 244), (46, 130), (46, 44)]
d.polygon(shield, fill=(28, 78, 168, 255), outline=(255, 255, 255, 255), width=6)

# 顶部高光
d.line([(58, 56), (198, 56)], fill=(92, 140, 220, 255), width=8)

# 五角星
cx, cy, R, r = 128, 120, 64, 27
pts = []
for i in range(10):
    rad = R if i % 2 == 0 else r
    ang = -math.pi / 2 + i * math.pi / 5
    pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
d.polygon(pts, fill=(255, 196, 0, 255), outline=(255, 255, 255, 255), width=4)

img.save("icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icon.ico saved")
