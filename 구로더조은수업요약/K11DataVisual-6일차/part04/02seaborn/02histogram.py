# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns
'''
히스토그램 : 도수분포표를 그래프로 나타낸 것이다. 
    변수가 하나인 단변수 데이터의 빈도수를 표현하다. x축을 같은 크기의
    여러구간으로 나누고 각 구간에 속하는 데이터값의 갯수를 y축에 표시한다.
도수분포표 : 도수 분포는 표본의 다양한 산출 분포를 보여주는 표이다. 
    가령 성인 30명을 대상으로 하루동안 사용하는 문자의 건수를 조사하여
    10~20건, 20~30건에 각 몇명이 분포하는지를 표시한다. 
커널밀도그래프 : 주어진 데이터를 정규화시켜 넓이가 1이 되도록 그린 그래프.
'''
#타이타닉 데이터셋을 로드한다. 
titanic = sns.load_dataset('titanic')
sns.set_style('darkgrid')

#Axe객체를 생성하여 3개의 영역으로 나눈다. 수평방향으로 그래프가 표시된다.
fig = plt.figure(figsize=(15, 5))
axe1 = fig.add_subplot(1,3,1)
axe2 = fig.add_subplot(1,3,2)
axe3 = fig.add_subplot(1,3,3)

#히스토그램+커널밀도그래프를 출력한다. 
sns.distplot(titanic['fare'], ax=axe1)
#커널밀도그래프
sns.kdeplot(x='fare', data=titanic, ax=axe2)
#히스토그램
sns.histplot(x='fare', data=titanic, ax=axe3)

#타이틀 설정
axe1.set_title('titanic fare - hist/ked')
axe2.set_title('titanic fare - ked')
axe3.set_title('titanic fare - hist')

#그래프를 보면 대부분 100불 미만에 집중된것을 볼수있다. 
plt.show()


