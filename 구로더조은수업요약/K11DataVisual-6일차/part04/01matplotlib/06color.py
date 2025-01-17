# -*- coding: utf-8 -*-
import matplotlib

colors = {}

#맷플롯립에서 제공하는 색깔의 목록을 확인한다. 
for name, hex in matplotlib.colors.cnames.items():
    colors[name] = hex

print(colors)
