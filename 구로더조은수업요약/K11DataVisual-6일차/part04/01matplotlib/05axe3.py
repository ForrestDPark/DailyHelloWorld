# -*- coding: utf-8 -*-
#모듈 임포트
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

#폰트설정
font_path = "../data/malgun.ttf" 
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

#서울에서 다른 지역으로 이동한 데이터를 Excel로부터 추출
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', engine='openpyxl', 
                   header=0)
df = df.fillna(method='ffill')
mask = (df['전출지별'] == '서울특별시') & (df['전입지별'] != '서울특별시') 
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
##마스크적용, 컬럼삭제 및 인덱스 지정까지 진행한다.  

#년도 적용을 위해 리스트를 생성한다. 1970~2017까지 지정한다. 
col_years = list(map(str, range(1970, 2018)))
#서울에서 각 3개의 도로 이동한 데이터를 추출한다. 
df3 = df_seoul.loc[['충청남도','경상북도','강원도'], col_years]
#그래프 스타일 지정
plt.style.use('ggplot')
#그래프 크기 지정
fig = plt.figure(figsize=(20,5))
#Axe객체를 1개만 생성한다. 
axe = fig.add_subplot(1,1,1)
#한 그래프에 3개의 꺽은선을 표현한다. 
#df3.loc['충청남도',:] => '충청남도' 행의 전체기간(열)을 선택한다. 
axe.plot(col_years, df3.loc['충청남도',:], marker='o', 
         markerfacecolor='green', markersize=10, color='olive', 
         linewidth=2, label='서울 -> 충남')
axe.plot(col_years, df3.loc['경상북도',:], marker='o', 
         markerfacecolor='blue', markersize=10, color='skyblue', 
         linewidth=2, label='서울 -> 경북')
axe.plot(col_years, df3.loc['강원도',:], marker='o', 
         markerfacecolor='red', markersize=10, color='magenta', 
         linewidth=2, label='서울 -> 강원')
#범례, 타이틀, 라벨 등을 지정한다. 
axe.legend(loc='best')
axe.set_title('서울->충남, 경북, 강원 인구이동', size=20)
axe.set_xlabel('기간', size=12)
axe.set_ylabel('이동인구수', size=12)
axe.set_xticklabels(col_years, rotation=90)
#축 눈금 라벨의 크기를 지정한다. 
axe.tick_params(axis="x", labelsize=10)
axe.tick_params(axis="y", labelsize=10)

plt.show()

 





