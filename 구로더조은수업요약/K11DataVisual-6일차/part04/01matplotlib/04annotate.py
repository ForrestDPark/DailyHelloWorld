# -*- coding: utf-8 -*-
#모듈 임포트
import pandas as pd
import matplotlib.pyplot as plt

#한글처리
from matplotlib import font_manager, rc
font_path = "../data/malgun.ttf"
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

#엑셀을 데이터프레임으로 변환(서울->경기도로 이동한 데이터만 추출)
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', engine='openpyxl', header=0)
df = df.fillna(method='ffill')
print(df.head())
mask = (df['전출지별']=='서울특별시') & (df['전입지별']!='서울특별시')
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
print(df_seoul)
sr_one = df_seoul.loc['경기도']
print(sr_one)

#그래프의 스타일과 크기, 마커 설정
plt.style.use('ggplot')
plt.figure(figsize=(14, 5))  
plt.xticks(rotation='vertical')
plt.plot(sr_one.index, sr_one.values, marker='o', markersize=10) 

#그래프의 타이틀 및 라벨 설정
plt.title('서울 -> 경기 인구 이동')
plt.xlabel('기간')
plt.ylabel('이동 인구수')
plt.legend(labels=['서울->경기'], loc='best') 

#y축에 표시할 데이터의 범위를 지정한다.(최소값, 최대값) 
plt.ylim(50000, 800000)

#그래프에 주석을 표시한다.(첫번째와 두번째는 화살표)
'''
위치를 나타내는 x,y좌표에서 x는 인덱스 번호를 사용한다. (0:1970, 1:1971)
y는 인구수를 나타내는 숫자이므로 그대로 사용할 수 있다. 
즉 (2,290000)이라면 1972년의 29만의 좌표가 된다. 

va : 글자를 위아래 세로방향으로 정렬한다. center, top, bottom, baseline
ha : 좌우 방향으로 정렬한다. center, left, right
'''
plt.annotate('',                 #텍스트 표시(여기서는 생략)
             xytext=(2, 290000), #화살표의 꼬리부분(시작점)  
             xy=(20, 620000),    #화살표의 머리부분(끝점)  
             xycoords='data',    #좌표체계(데이터를 사용함)   
             #화살표의 속성 : 모양, 색깔, 두께를 딕셔너리로 지정한다.
             arrowprops=dict(arrowstyle='->', color='skyblue', lw=2),
        )  
plt.annotate('',
             xytext=(30, 580000),   
             xy=(47, 450000),       
             xycoords='data',       
             arrowprops=dict(arrowstyle='->', color='olive', lw=5), 
        )
#그래프의 텍스트 주석을 표시한다. 
plt.annotate('인구이동 증가(1970-1995)',  #출력할 텍스트 입력
             xy=(10, 450000),            #텍스트의 위치
             rotation=25,                #회전각도
             va='baseline',              #텍스트의 수직방향정렬
             ha='center',                #텍스트의 수평방향정렬
             fontsize=15,                #텍스트크기
        )
plt.annotate('인구이동 감소(1995-2017)', 
             xy=(40, 560000),           
             rotation=-10,              
             va='baseline',             
             ha='center',              
             fontsize=15,              
        )
#앞의 모든 설정을 저장한 후 그래프를 출력한다.
plt.show() 














