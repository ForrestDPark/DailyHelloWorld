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
 

col_years = list(map(str, range(1970, 2018)))
df3 = df_seoul.loc[['충청남도','경상북도','강원도'], col_years]
plt.style.use('ggplot')
fig = plt.figure(figsize=(20,5))
axe = fig.add_subplot(1,1,1)

axe.plot(col_years, df3.loc['충청남도',:], marker='o', markerfacecolor='green', 
        markersize=10, color='olive', linewidth=2, label='서울 -> 충남')
axe.plot(col_years, df3.loc['경상북도',:], marker='o', markerfacecolor='blue', 
        markersize=10, color='skyblue', linewidth=2, label='서울 -> 경북')
axe.plot(col_years, df3.loc['강원도',:], marker='o', markerfacecolor='red', 
        markersize=10, color='magenta', linewidth=2, label='서울 -> 강원')

axe.legend(loc='best')
axe.set_title('서울->충남, 경북, 강원 인구이동', size=20)

axe.set_xlabel('기간', size=12)
axe.set_ylabel('이동인구수', size=12)
axe.set_xticklabels(col_years, rotation=90)

axe.tick_params(axis="x", labelsize=10)
axe.tick_params(axis="y", labelsize=10)

plt.show()

 





