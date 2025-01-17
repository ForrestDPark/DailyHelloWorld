# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns

titanic = sns.load_dataset('titanic')
#데이터셋의 상위 5개를 출력한다. 
print(titanic.head()) 
#인자값이 있으면 그만큼의 데이터를 출력한다.(5개가 디폴트값)
print(titanic.tail(10)) 
#컬럼의 정보를 출력한다. 컬럼명과 데이터타입 등
print(titanic.info())
#수치형 컬럼에 대한 요약 통계를 보여준다. 
print(titanic.describe()) 
#문자형 컬럼에 대한 통계를 보여준다. 
print(titanic.describe(include='object'))
#특정 컬럼의 값의 분포를 확인한다. who는 남자,여자,아이의 분포를 출력한다.
print(titanic['who'].value_counts())

#그래프의 기본스타일 및 Axe객체 3개를 가로형으로 생성한다.
sns.set_style('whitegrid')
fig = plt.figure(figsize=(15, 5))
axe1 = fig.add_subplot(1,3,1)
axe2 = fig.add_subplot(1,3,2)
axe3 = fig.add_subplot(1,3,3)

'''
막대그래프를 그린다. x축은 성별, y축은 구조여부를 설정한다. 
hue : 해당 옵션은 bar를 새로운 기준으로 분할한다. 즉 좌석등급으로
    분할한다. 
dodge : 데이터를 위로 누적하여 출력한다. 즉, 막대그래프를 겹쳐서 표현한다. 
'''
sns.barplot(x='sex', y='survived', data=titanic, ax=axe1)
sns.barplot(x='sex', y='survived', hue='class', data=titanic, 
            ax=axe2)
sns.barplot(x='sex', y='survived', hue='class', dodge=False, 
            data=titanic, ax=axe3)

axe1.set_title('titanic survived - sex')
axe2.set_title('titanic survived - sex/class')
axe3.set_title('titanic survived - sex/class(stacked)')

plt.show()

