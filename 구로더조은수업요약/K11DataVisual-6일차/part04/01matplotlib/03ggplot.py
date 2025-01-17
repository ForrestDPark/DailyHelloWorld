# -*- coding: utf-8 -*-
#모듈 임포트
import pandas as pd
import matplotlib.pyplot as plt
#from matplotlib import font_manager, rc 
from matplotlib import rc # 맥

#폰트설정
#font_path = "../data/malgun.ttf"
#font_name = font_manager.FontProperties(fname=font_path).get_name()
#rc('font', family=font_name)

rc('font', family='AppleGothic') # 맥
plt.rcParams['axes.unicode_minus'] = False # 맥

#서울->경기 데이터를 Excel로부터 추출
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', 
                   engine= 'openpyxl', header=0)
df = df.fillna(method='ffill')
mask = (df['전출지별'] == '서울특별시') & (df['전입지별'] != '서울특별시') 
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
sr_one = df_seoul.loc['경기도']

#그래프 스타일 지정 : ggplot과 같은 스타일은 아래에서 참조한다.
# https://matplotlib.org/stable/gallery/style_sheets/style_sheets_reference.html
#plt.style.use('dark_background')
plt.style.use('ggplot')
#그림 사이즈 지정(가로, 세로의 크기를 지정할 수 있다.)
plt.figure(figsize=(14,5))
#x축 라벨 회전
plt.xticks(size=10, rotation='vertical')
#그래프에 마커와 마커사이즈를 지정하여 꺽은선 부분에 표시한다.
plt.plot(sr_one.index, sr_one.values, marker='o', markersize=10) 
#그래프의 타이틀과 폰트크기를 지정한다. 
plt.title('서울 -> 경기 인구 이동', size=30) 
plt.xlabel('기간', size=20)
plt.ylabel('이동 인구수', size=20)
#범례표시
plt.legend(labels=['서울->경기'], loc='best', fontsize=15) 
#그래프 출력
plt.show()