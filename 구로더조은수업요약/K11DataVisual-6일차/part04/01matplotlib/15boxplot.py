# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

font_path = "../data/malgun.ttf"  
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

'''
박스플롯
: 범주형 데이터의 분포를 파악하는데 적합하다. 
최소, 최대, 1분위값, 중간값, 2분위값 등을 제공한다. 
'''
#스타일 서식 지정
plt.style.use('seaborn-poster')
#마이너스 부호 출력 설정
plt.rcParams['axes.unicode_minus']=False

#데이터프레임 생성 및 열지정
df = pd.read_csv('../data/auto-mpg.csv', header=None)
df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

#그래프의 크기 지정 후 Axe객체를 2개 생성한다. 
fig = plt.figure(figsize=(15, 5))  
ax1 = fig.add_subplot(1, 2, 1) 
ax2 = fig.add_subplot(1, 2, 2)

#Axe객체에 boxplot() 메서드로 그래프를 생성한다. 
#origin(제조국가별) mpg(연비) 분포를 출력한다. 
ax1.boxplot(x=[df[df['origin']==1]['mpg'],
               df[df['origin']==2]['mpg'],
               df[df['origin']==3]['mpg']], 
         labels=['USA', 'EU', 'JAPAN'])
'''
vert=False 해당 옵션을 위해 위쪽은 수직형으로 아래쪽은 수평형으로
그래프가 설정된다. 즉 vert(vertical)는 True가 디폴트값이다. 
'''
ax2.boxplot(x=[df[df['origin']==1]['mpg'],
               df[df['origin']==2]['mpg'],
               df[df['origin']==3]['mpg']], 
         labels=['USA', 'EU', 'JAPAN'],
         vert=False)

#타이틀 지정
ax1.set_title('제조국가별 연비 분포(수직 박스 플롯)')
ax2.set_title('제조국가별 연비 분포(수평 박스 플롯)')

'''
그래프의 상단 혹은 우측에 o로 표시되는값이 있는데 , 보통 관측되는
데이터의 범위에서 많이 벗어난 값으로 '이상치'라고 표현한다. 
'''
plt.show()




