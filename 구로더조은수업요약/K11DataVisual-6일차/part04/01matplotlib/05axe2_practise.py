# -*- coding: utf-8 -*-
#모듈 임포트
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

#폰트설정
font_path = "../data/malgun.ttf" 
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

#서울->경기 데이터를 Excel로부터 추출(원본)
'''
연습문제] 위 데이터를 강원도->서울특별시로 이동한 데이터를 추출하여 
    아래 그래프에 적용하시오. 단 기간은 1980년부터 마지막까지로 
    지정하시오. 이에 맞게 라벨도 수정하시오.
'''
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', engine='openpyxl', 
                   header=0)
df = df.fillna(method='ffill')
#강원도->서울 이므로 수정필요
mask = (df['전출지별'] == '강원도') & (df['전입지별'] != '강원도') 
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
print(df_seoul)
#데이터 중에서 서울에서 이동한것만 추출. 또한 년도가 열이므로 1980~끝까지
#의 데이터를 선택하여 추출한다. 
sr_one = df_seoul.loc['서울특별시', '1980':]
print(sr_one)

#######################

#그래프 스타일 지정
plt.style.use('ggplot')
#그래프의 크기 지정 및 틀 생성
fig = plt.figure(figsize=(20, 5))
#2행 1열중 1첫번째 영역에 Axe객체 생성
ax1 = fig.add_subplot(2, 1, 1)  
#axe객체에 plot함수로 그래프를 생성한다.(속성은 PPT자료 참조) 
ax1.plot(sr_one , marker='o', markersize=10, markerfacecolor='orange',
         color='olive', linewidth=2, label='강원도->서울')
#범례표시
ax1.legend(loc='best')
#y축 범위 지정(수정필요)
ax1.set_ylim(0, 100000)
#그래프의 제목 (수정필요)
ax1.set_title('강원 -> 서울 인구 이동', size=20)
#각 축의 라벨 지정
ax1.set_xlabel('기간', size=12)
ax1.set_ylabel('이동인구수', size=12)
#x축 라벨 지정 및 75도 회전
ax1.set_xticklabels(sr_one.index, rotation=75)
#축 눈금 라벨 크기 지정
ax1.tick_params(axis='x', labelsize=20)
ax1.tick_params(axis='y', labelsize=10)

plt.show()

