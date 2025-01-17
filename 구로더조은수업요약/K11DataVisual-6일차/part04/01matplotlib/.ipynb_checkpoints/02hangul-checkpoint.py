# -*- coding: utf-8 -*-
#모듈 임포트 

import pandas as pd
import matplotlib.pyplot as plt

#한글깨짐 처리를 위해 폰트를 설정한다.  
#from matplotlib import font_manager, rc
import matplotlib.font_manager as fm

#폰트의 경로 설정
font_path = "../data/malgun.ttf"
#폰트파일의 이름을 속성으로 지정한다. 
font_name = fm.FontProperties(fname=font_path).get_name()
#폰트를 적용한다. 
plt.rc('font', family=font_name)
 
#엑셀을 데이터프레임으로 변환 후 서울에서 경기도로 전출한 데이터만 추출한다. 
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', 
                   engine='openpyxl', header=0)
df = df.fillna(method='ffill')
#print(df.head()) 
mask = (df['전출지별']=='서울특별시') & (df['전입지별']!='서울특별시')
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
#print(df_seoul)
sr_one = df_seoul.loc['경기도']
print(sr_one)

#그래프의 추가적인 설정을 한다. 
#그림의 사이즈를 설정한다.  
plt.figure(figsize=(14, 5))  

#x축의 라벨을 수직방향으로 설정한다.(글자가 겹쳐지는 부분 처리)
#plt.xticks(rotation='vertical')
#plt.xticks(rotation=90) #90인 경우 vertical과 동일하다.
#라벨설정시 정수형으로 기술해도된다. 
plt.xticks(rotation=300)

#x, y축 데이터를 plot함수에 입력한다. 
plt.plot(sr_one.index, sr_one.values)
#타이틀 및 라벨을 설정한다. 
plt.title('서울 -> 경기 인구 이동')
plt.xlabel('기간')
plt.ylabel('이동 인구수')
#범례 표시(그래프의 우측 상단에 표시된다)
plt.legend(labels=['서울->경기'], loc='best') 
#그래프를 출력한다. 
plt.show() 

















