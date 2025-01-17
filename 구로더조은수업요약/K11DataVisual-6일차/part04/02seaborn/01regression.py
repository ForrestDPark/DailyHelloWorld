# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns
'''
regplot() : 회귀선이 있는 산점도를 표현한다. 
    서로다른 2개의 연속 변수 사이의 산점도를 그리고 선형회귀분석에
    의한 회귀선을 함께 출력한다. 
'''
#Seaborn에서 제공하는 타이타닉 데이터셋을 가져온다. 
#탑승자 891명에 대한 정보가 저장되어있다. 
titanic = sns.load_dataset('titanic')
#스타일 테마설정(5가지:darkgrid, whitegrid, dark, white, ticks)
sns.set_style('darkgrid')

#그래프의 크기 설정 및 2개의 Axe객체 생성
fig = plt.figure(figsize=(15, 5))
#1행 2열로 지정한 후 가로형으로 2개의 그래프를 표현한다. 
axe1 = fig.add_subplot(1,2,1)
axe2 = fig.add_subplot(1,2,2)
'''
x축은 나이, y축은 운임요금에 대한 관계를 그래프로 표현한다. 
fit_reg옵션은 선형회귀선을 표시하기 위한것으로 True가 디폴트값이다.
즉 False면 표시하지 않는다. 
'''
sns.regplot(x='age', y='fare', data=titanic, ax=axe1)
sns.regplot(x='age', y='fare', data=titanic, ax=axe2, fit_reg=False)

plt.show()

