# -*- coding: utf-8 -*-
'''
보조축을 추가하여 2개의 y축을 갖는 그래프를 그려본다. 
기존(좌측)축 : 연도별 북한의 발전량을 막대그래프로 표시
보조(우측)축 : 북한 발전량의 전년 대비 증감률을 백분률로 계산하여
    선 그래프에 표시한다. 
    
Axe1은 세로형 막대그래프, Axe2는 꺽은선그래프를 그린다.     
'''
#라이브러리 임포트
import pandas as pd
import matplotlib.pyplot as plt

#한글깨짐처리 
from matplotlib import font_manager, rc
font_path = "../data/malgun.ttf"
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

#스타일 서식 지정
plt.style.use('ggplot')
#마이너스 부호 출력 설정
plt.rcParams['axes.unicode_minus'] = False
#엑셀파일을 읽어 데이터프레임을 만든다. header옵션이 없으므로 첫행은
#타이틀로 지정된다. 
df = pd.read_excel('../data/남북한발전전력량.xlsx', engine='openpyxl') 
#인덱스 0은 남한의 합계가 되므로, 5~8행까지 즉 북한의 합계~원자력을 선택한다.
df = df.loc[5:9] 
#컬럼을 찾아서 삭제한다. 그리고 데이터프레임에 적용한다. 
df.drop('전력량 (억㎾h)', axis='columns', inplace=True)
#해당 컬럼을 인덱스로 지정한다. 
df.set_index('발전 전력별', inplace=True)
print(df)
#데이터프레임을 전치한다. 
df = df.T 
print(df)

#증감율(변동률) 계산을 위해 합계를 총발전량으로 이름을 변경한다. 
df = df.rename(columns={'합계':'총발전량'})
#총발전량 열의 데이터를 1행씩 뒤로 이동시켜 새로운 컬럼을 생성한다. 
df['총발전량 - 1년'] = df['총발전량'].shift(1);
print(df)
#증감률을 계산하여 새로운 컬럼을 생성한다. 
df['증감률'] = ((df['총발전량']/df['총발전량 - 1년']) - 1) * 100

#수력, 화력 데이터를 이용해서 2개의 축을 가진 그래프를 그린다. 
#수직형 막대그래프를 겹쳐지지 않는 형태로 출력한다. 
axe1 = df[['수력','화력']].plot(kind='bar', figsize=(20,10), 
                            width=0.7, stacked=True)
#twinx() 함수로 Axe객체의 복사본을 만든다. 
axe2 = axe1.twinx()
#생성된 복사본은 꺽은선 그래프를 그린다. ls='--' 옵션은 선 스타일을
#점선으로 설정한다. 
axe2.plot(df.index, df.증감률, ls='--', marker='o', markersize=20,
          color='red', label='전년대비 증감률(%)')

#y축의 범위 설정
axe1.set_ylim(0, 500)
axe2.set_ylim(-50, 50)

#각종 라벨 설정
axe1.set_xlabel('연도', size=20)
axe1.set_ylabel('발전량(억 KWh)')
axe2.set_ylabel('전년 대비 증감률(%)')

#타이틀 및 범례 설정
plt.title('북한 전력 발전량 (1990~2016)', size=30)
axe1.legend(loc='upper left')
 
#모든 설정을 저장한 후 그래프를 출력한다. 
plt.show()