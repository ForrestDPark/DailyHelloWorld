# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

#폰트설정
font_path = "../data/malgun.ttf" 
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', engine= 'openpyxl', header=0)
df = df.fillna(method='ffill')
mask = (df['전출지별'] == '서울특별시') & (df['전입지별'] != '서울특별시') 
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)

col_years = list(map(str, range(1970, 2018)))
df4 = df_seoul.loc[['충청남도','경상북도', '강원도', '전라남도'], col_years]
######## 앞의 예제와 동일함.

#데이터프레임을 전치한다. 즉 행과 열을 바꾼다. 
df4 = df4.transpose()
#챠트 스타일 서식 지정
plt.style.use('ggplot')
#데이터프레임의 인덱스를 정수형으로 변경한다.(x축 눈금 라벨 표시)
df4.index = df4.index.map(int)

'''
면적 그래프 그리기
    kind='area' : 면적 그래프를 그리기 위한 옵션
    stacked=False : 그래프를 겹쳐서 표현한다. 
            True : 그래프가 겹쳐지지 않는다. 
    alpha=0.2 : 그래프의 투명도를 설정한다. 0~1사이로 숫자가 작을수록
        투명해진다. 
'''
#df4.plot(kind='area', stacked=False, alpha=0.2, figsize=(20,10))
df4.plot(kind='area', stacked=True, alpha=0.2, figsize=(20,10))

#그래프의 타이틀, 라벨, 범례를 설정한다. 
plt.title('서울 -> 타시도 인구 이동', size=30)
plt.ylabel('이동 인구 수', size=20)
plt.xlabel('기간', size=20)
plt.legend(loc='best', fontsize=15)

plt.show()

