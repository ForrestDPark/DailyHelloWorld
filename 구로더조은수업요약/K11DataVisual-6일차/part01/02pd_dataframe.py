# -*- coding: utf-8 -*-
'''
데이터프레임(Dataframe)
: 1차원배열 형태인 시리즈가 여러개 모여있는 형태로 2차원배열
과 동일하다. R의 데이터프레임을 착안하여 만들어지게 되었다.
행(Row)과 열(column)로 구성된다. 
''' 
import pandas as pd

'''열(컬럼명)의 이름을 key로 리스트를 value로 갖는 딕셔너리
를 정의한다. (이처럼 여러줄에 걸쳐 한문장이 완성되는 경우
블럭으로 지정한 후 실행해야한다.)
'''
dict_data = {'c0':[1,2,3], 'c1':[4,5,6], 
             'c2':[7,8,9], 'c3':[10,11,12], 
             'c4':[13,14,15]}
#딕셔너리를 데이터프레임으로 변환한다.
df = pd.DataFrame(dict_data)
'''key는 열이되고, value는 각 행의 데이터가 된다. 이경우
별도의 인덱스를 부여하지 않았으므로 정수형 인덱스가 자동으로
부여된다. '''
print('타입', type(df))
print('데이터프레임1\n', df)

#인덱스와 컬럼명을 지정해서 데이터프레임을 생성한다. 
#인덱스는 행(Row)이되고, 컬럼은 열(Column)로 지정된다.
df = pd.DataFrame([[20, '남', '부산'], [17, '여', '서울']], 
                  index=['철수', '영희'], 
                  columns=['나이', '성별', '지역'])
print('데이터프레임2\n',df)     
#인덱스와 컬럼만 리스트로 추출하여 출력한다. 
print(df.index) 
print(df.columns) 

#변경1 : 인덱스와 컬럼명을 속성을 통해 변경한다. 
df.index=['학생1', '학생2']
df.columns=['연령', '남녀', '거주']
print(df)    

#변경2 : rename() 함수를 통해 변경한다. 
'''만약 원본객체를 수정하고 싶다면 inplace=True옵션을 
추가한다. 해당 옵션이 없다면 False가 디폴트값이므로 새로운
객체를 반환하게된다.'''
df.rename(columns={'연령':'No', '남녀':'Gender', '거주':'City'}, 
          inplace=True)
df.rename(index={'학생1':'Student1', '학생2':'Student2'}, 
          inplace=True)
print(df)

'''
loc : 인덱스명으로 하나의 행을 선택한다. 
iloc : 정수형 인덱스를 통해 행을 선택한다. 
'''
stu1 = df.loc['Student1'] 
stu2 = df.iloc[1] 
print(stu1, stu2)

'''
삭제하기 : drop()을 통해 행 혹은 열을 삭제한다. 
축 옵션
    행삭제 : axis=0 혹은 입력안함. 즉 행이 default값
    열삭제 : axis=1
여러개를 동시에 삭제할때는 리스트 형태로 입력한다. 
'''
df.drop('Student1', inplace=True)
print(df)

#Gender라는 행이 없으므로 오류가 발생된다. 
#df.drop('Gender')
#열(컬럼)에 대한 삭제이므로 정상적으로 동작한다. 
#단 inplace옵션이 없으므로 기존객체에는 적용되지 않는다.
df.drop('Gender', axis=1) 
#여기서 실행했을때 기존객체에 적용된다. 
df.drop('Gender', axis=1, inplace=True) 
print(df)








