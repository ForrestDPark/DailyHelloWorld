# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
'''
판다스의 산술연산
    1단계 : 행/열 인덱스를 기준으로 원소를 정렬한다. 
    2단계 : 동일한 위치에 있는 원소끼리 일대일로 대응한다. 
    3단계 : 일대일 대응이 되는 원소끼리 연산을 처리한다. 그외에는
        NaN으로 처리된다. 
'''
#딕셔너리를 시리즈 객체로 만든다. 
student1 = pd.Series({'국어':100, '영어':80, '수학':90})
print(student1)

#학생의 점수를 200으로 나눈다. 전체 데이터에 적용된다. 
percentage = student1 / 200
print(percentage)

#두번째 시리즈 생성. Numpy모듈의 nan을 통해 NaN으로 초기화한다. 
student2 = pd.Series({'수학':80, '국어':np.nan, '영어':80})
print(student2)

'''
사칙연산은 add(), sub(), mul(), div() 메서드를 사용할 수 있다. 
공통 인덱스가 없거나 NaN이 포함되어 있으면 연산결과는 NaN이 된다. 
fill_value를 사용하면 NaN인 경우 지정한 값으로 대체할 수 있다. 
'''
addition = student1 + student2 
subtraction = student1 - student2
multiplication = student1.mul(student2, fill_value=0) 
division = student1.div(student2, fill_value=0) 

#연산의 결과는 시리즈이므로 이를 통해 데이터프레임을 생성한다. 
result = pd.DataFrame([addition, subtraction, multiplication, division], 
                      index=['덧셈', '뺄셈', '곱셈', '나눗셈'])
print(result)

