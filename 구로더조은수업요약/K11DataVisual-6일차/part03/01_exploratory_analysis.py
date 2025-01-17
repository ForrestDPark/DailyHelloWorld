# -*- coding: utf-8 -*-
import pandas as pd

'''
auto-mpg.csv
: 자동차 연비를 데이터셋으로 구성한 파일이다. 
연비, 실린더수, 배기량 등의 데이터로 구성되어있다. 
'''
#CSV 파일을 데이터프레임으로 변환한다. 타이틀 없이 모든 데이터를 사용할
#것이므로 header=none으로 지정한다. 
df = pd.read_csv('./data/auto-mpg.csv', header=None)
# [연비, 실린더, 배기량, 마력, 무게, 가속능력, 연식, 제조국, 자동차명]
df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

# 데이터프레임의 일부 데이터를 확인할때 사용한다. 
# 처음 5개의 행
print(df.head())
# 마지막 5개의 행
print(df.tail())

# df의 모양과 크기 확인 : 행의갯수, 열의개수를 튜플로 반환한다. 
print(df.shape)
#내용 확인 : 클래스유형, 행인덱스, 열의이름과갯수, 자료형 등이 출력된다.
print(df.info())
#자료형 확인
'''
int64 : 정수형
float64 : 실수형
object : 문자형
datetime64, timedelta64 : 날짜 및 시간
'''
print(df.dtypes) #데이터프레임 전체의 자료형 확인
print(df.mpg.dtypes) #특정 컬럼의 자료형 확인
print(df.cylinders.dtypes)

#데이터 출력
'''
데이터프레임의 기술통계 정보를 확인한다. 산술 데이터를 갖는 열에 대한
평균, 표준편차 등을 출력한다. 
'''
print(df.describe()) 
'''
산술데이터가 아닌 열에 대한 정보를 포함하여 출력하므로 NaN이 나올수도
있다. 
'''
print(df.describe(include='all')) 

#유효한 원소의 갯수 : 각 열이 가지고 있는 원소의 갯수 표시
print(df.count())
#각 열의 데이터갯수는 시리즈 객체로 반환된다. 
print(type(df.count()))  

#특정 열의 고유값
'''
origin 열은 제조국가 데이터를 표현한다. 
1 : 미국(USA)
2 : 유럽(EU)
3 : 일본(JPN)
'''
unique_values = df['origin'].value_counts() 
print(unique_values)
 
'''
통계함수 : 데이터프레임의 기술 통계 정보를 확인하는 함수들로
    평균, 표준편차, 최대, 최소, 중간값 등을 표현한다. 
    count() : 데이터의 갯수
    mean() : 평균값
    max(), min() : 최대, 최소값 
    std() : 표준편차
        ※표준편차란 평균에 대한 오차를 뜻한다. 실제 데이터 값이 평균을
        기준으로 얼만큼 기복이 있는지를 나타내는 지표이다. 
        -집단1 : 172 174 176 178 180
        -집단2 : 176 176 176 176 176 
        위 두집단의 평균은 둘다 176이지만 표준편차는 각각 2.823, 0이
        된다. 즉 집단2가 좀더 신뢰성이 높은 데이터라 할수있다. 
'''
# 평균값 
print(df.mean())  
print(df['mpg'].mean()) #연비의 평균값
print(df.mpg.mean())
print(df[['mpg','weight']].mean()) #2개 이상의 평균값 

# 중간값 
print(df.median())
print(df['mpg'].median())
print(df['origin'].median())
'''
평균과 중간값의 차이
: 평균은 원소를 더한 후 갯수로 나누는것이고, 중간값은 원소들을 
한줄로 나열한 후 가장 가운데 있는 값을 뜻한다. 
즉, 평균은 산술값이고 중간값은 위치값이라 할 수 있다. 
'''
 
# 최대값 
'''
horsepower(마력) 컬럼의 경우 문자열이므로 아스키코드로 변환후 비교한다. 
하지만 중간에 ?가 포함되어있어 다른 숫자까지 문자열로 인식하여 결과가
제대로 나오지 않는다.
''' 
print(df.max()) #전체 데이터의 최대값
print(df['mpg'].max()) #연비의 최대값
print(df['horsepower'].max()) #마력의 최대값 
 
# 최소값 
print(df.min())
print(df['mpg'].min())
 
# 표준편차 
print(df.std())
print(df['mpg'].std())

# 상관계수 
'''
두 변수가 얼마나 서로 관련을 맺고 있는지를 수치화한것으로 
-1 ~ 1 사이에서 표현된다. 
0인경우 : 서로 관련이 없다.
1혹은 -1인 경우 : 양의관계(정비례) 이거나 음의관계(반비례)가 있다. 
'''
print(df.corr())
print(df[['mpg','weight']].corr())



















