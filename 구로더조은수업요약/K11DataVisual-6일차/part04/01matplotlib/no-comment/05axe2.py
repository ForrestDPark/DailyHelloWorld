# -*- coding: utf-8 -*-
#모듈 임포트
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

#폰트설정
font_path = "./data/malgun.ttf" 
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

#서울->경기 데이터를 Excel로부터 추출
df = pd.read_excel('./data/시도별 전출입 인구수.xlsx', engine='openpyxl', 
                   header=0)
df = df.fillna(method='ffill')
mask = (df['전출지별'] == '서울특별시') & (df['전입지별'] != '서울특별시') 
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
sr_one = df_seoul.loc['경기도']


plt.style.use('ggplot')

fig = plt.figure(figsize=(20, 5))
ax1 = fig.add_subplot(2, 1, 1)  

ax1.plot(sr_one, marker='o', markersize=10, markerfacecolor='orange',
         color='olive', linewidth=2, label='서울->경기')
ax1.legend(loc='best')
ax1.set_ylim(50000, 800000)
ax1.set_title('서울 -> 경기 인구 이동', size=20)
ax1.set_xlabel('기간', size=12)
ax1.set_ylabel('이동인구수', size=12)
ax1.set_xticklabels(sr_one.index, rotation=75)

ax1.tick_params(axis='x', labelsize=10)
ax1.tick_params(axis='y', labelsize=10)

plt.show()

