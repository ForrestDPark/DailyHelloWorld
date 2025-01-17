# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

#폰트설정
font_path = "../data/malgun.ttf" 
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

#서울에서 전출한 데이터를 Excel로부터 추출
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', engine= 'openpyxl', 
                   header=0)
df = df.fillna(method='ffill')
mask = (df['전출지별'] == '서울특별시') & (df['전입지별'] != '서울특별시') 
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)

#시작년도만 수정
col_years = list(map(str, range(2010, 2018))) 
df4 = df_seoul.loc[['충청남도','경상북도', '강원도', '전라남도'], col_years]
#####앞의 예제와 동일함

#2010~2017년 사이에 이동한 인구수를 합하여 새로운 열로 추가한다.
df4['합계'] = df4.sum(axis=1)
print(df4)
#새롭게 생성한 '합계'열을 오름차순으로 정렬한다. 
df_total = df4[['합계']].sort_values(by='합계', ascending=True)
print(df_total)

#그래프 스타일 지정
plt.style.use('ggplot')

#수평 막대 그래프를 생성한다. 
df_total.plot(kind='barh', figsize=(20,10), width=0.7, 
         color='cornflowerblue')

#라벨지정 및 범위설정
plt.title('서울 -> 타시도 인구 이동', size=30)
plt.ylabel('전입지', size=20)
plt.xlabel('이동인구수', size=20)

plt.show()
