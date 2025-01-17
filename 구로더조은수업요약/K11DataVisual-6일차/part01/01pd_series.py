# -*- coding: utf-8 -*-
# 판다스 라이브러리를 해당 문서에 임포트한다.
# 별칭으로 pd를 사용한다.  
import pandas as pd

'''
시리즈(Series)
: 시리즈는 데이터가 순차적으로 나열된 1차원배열
형태를 가진다. key와 Value로 구성된 딕셔너리와
비슷한 구조를 가지고있다. 
'''

# Key와 Value 구조를 가진 딕셔너리 선언
dict_data = {'a':1, 'b':2, 'c':3}
# 딕셔너리를 시리즈로 변환한다. 
sr = pd.Series(dict_data)
# 타입(자료형) 확인하기
print(type(sr))
# 출력하기 
print(sr)

# 여러가지 데이터를 리스트로 선언한 후 시리즈로 변환
list_data = ['2019-01-02', 3.14, 'ABC', 100, True]
#리스트는 Key가 없는 자료형이므로 변환시 정수형 위치 인덱스
#(Integer position)로 지정된다. 
sr = pd.Series(list_data)
#index속성은 시리즈에서 인덱스부분만 배열로 추출한다.
idx = sr.index
#values속성은 값 부분만 배열로 추출한다. 
val = sr.values
print(sr)
print(idx)
print(val)

#튜플 선언
tuple_data = ('유겸', '2012-04-03', '남', True)
#튜플을 시리즈로 변환하면 index옵션을 통해 문자열 인덱스를
#부여한다. 인덱스 부여시 갯수가 틀리거나, 매개변수의 순서를
#바꾸면 에러가 발생한다. 
sr = pd.Series(tuple_data, index=['이름', '생년월일', '성별', '학생여부'])
#순서를 바꾸면 에러발생됨
#sr = pd.Series(index=['이름', '생년월일', '성별', '학생여부'], tuple_data)
print(sr)
#정수형 인덱스를 통해 출력
print(sr[0])
#라벨형 인덱스를 통해 출력
print(sr['이름'])

#여러개의 원소를 선택할때는 정수형 혹은 라벨형 인덱스를 
#콤마로 구분해서 사용할 수 있다. 
print(sr[[1, 2]]) 
print(sr[['생년월일', '성별']])

#인덱스 범위를 정수형태로 사용하면 범위의 끝은 포함되지 
#않는다. 즉 1부터 2미만까지만 선택된다. 
print(sr[1 : 2]) 
#라벨(문자)형 인덱스를 사용하면 범위의 끝이 포함된다. 
#따람서 생년부터 학생여부까지 모든 데이터가 출력된다.
print(sr['생년월일' : '학생여부']) 

