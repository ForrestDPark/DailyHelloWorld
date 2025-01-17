import sys,os


class F:
    ### Functions ### 
    import pandas as pd, numpy as np
    # import matplotlib.pyplot as plt
    from pprint import pprint
    # 기본 세팅
    def colored_text(text, color='default', bold=False):
            '''
            #### 예시 사용법
            print(colored_text('저장 하지 않습니다.', 'red'))
            print(colored_text('저장 합니다.', 'green'))
            default,red,green,yellow,blue, magenta, cyan, white, rest
            '''
            colors = {
                'default': '\033[99m',
                'red': '\033[91m',
                'green': '\033[92m',
                'yellow': '\033[93m',
                'blue': '\033[94m',
                'magenta': '\033[95m', #보라색
                'cyan': '\033[96m',
                'white': '\033[97m',
                'bright_black': '\033[90m',  # 밝은 검정색 (회색)
                'bright_red': '\033[91m',  # 밝은 빨간색
                'bright_green': '\033[92m',  # 밝은 초록색
                'bright_yellow': '\033[93m',  # 밝은 노란색
                'bright_blue': '\033[94m',  # 밝은 파란색
                'bright_magenta': '\033[95m',  # 밝은 보라색
                'bright_cyan': '\033[96m',  # 밝은 청록색
                'bright_white': '\033[97m',  # 밝은 흰색
                'reset': '\033[0m'
            }
            color_code = colors.get(color, colors['default'])
            bold_code = '\033[1m' if bold else ''
            reset_code = colors['reset']
            
            return f"{bold_code}{color_code}{text}{reset_code}"
    def blue(str):return F.colored_text(str,'blue')
    def yellow(str):return F.colored_text(str,'yellow')
    def red(str):return F.colored_text(str,'red')
    def green(str):return F.colored_text(str,'green')

class chapter1:
    ########-- Chapter 1. input output   --- #######
    def practice():
        T  = int(sys.stdin.readline().rstrip())
        for i in range(T):
            a,b = map(int, sys.stdin.readline().split())
            print(f"Case #{i+1}:",a+b)
    def practice1():
        T  = int(sys.stdin.readline().rstrip())
        for i in range(T):
            a,b = map(int, sys.stdin.readline().split())
            print(f"Case #{i+1}: {a} + {b} = {a+b}")
    def starPrint():
        T  = int(sys.stdin.readline().rstrip())
        for i in range(T):
        
            print("*"*(i+1))
    def starPrint1():
        T  = int(sys.stdin.readline().rstrip())
        for i in range(T):
            a= "*"*(i+1)
            print(f"{a:>{T}}")
    def addFunc01():
        
        while True:
            a, b = map(int , sys.stdin.readline().split())
            if a==b==0:
                break
            else:
                print(a+b)
    def addFunc02():
        
        while True:
            try : 
                a, b = map(int , sys.stdin.readline().split())
                print(a+b)
            except: 
                break
class chapter2:
    ########-- Chapter 2. if  --- #######
    def countSelectedInteger():
        T = int(sys.stdin.readline())
        
        a = list(map(int, sys.stdin.readline().split()))
        selectNum = int(sys.stdin.readline())
        print(a.count(selectNum))
    def countLowerNumInArray():
        N , X = map(int,(sys.stdin.readline().split()))
        A  = list(map(int,(sys.stdin.readline().split())))
        for i in A :
            if i<X:
                print(i , end=" ")
    def minMax():
        N = int(sys.stdin.readline())
        intArr = list(map(int, sys.stdin.readline().split()))
        print(min(intArr), max(intArr))
class chapter3:
    ########-- Chapter 3. For  --- #######
    def findMaxInArray():
        import sys
        N =[]
        for i in range(9):
            N.append(int(sys.stdin.readline()))
        else:
            print(max(N), N.index(max(N))+1, sep="\n")
    def putBallInBasket():
        N , M = map ( int,sys.stdin.readline().split()) # M 은 횟수 N 은 바구니 수 
        baskets = {}
        for basket in range(N):
            baskets.update({basket+1:[]})
        # print(" 바구니 생성 완료")
        for m in range(M):
            i,j,k = map (int, sys.stdin.readline().split())
            # from i to j bucket -> input k
            for basket in range(i,j+1):
                if len(baskets[basket]) :
                    baskets[basket].pop()
                    baskets[basket].append(k)
                else:
                    baskets[basket].append(k)
        else:
            for i in baskets.keys():
                print(baskets[i][0] if len(baskets[i]) !=0 else 0, end =" ",)
    def changeBallsBetweenBasket():
        import sys
        N , M = map ( int,sys.stdin.readline().split()) # M 은 횟수 N 은 바구니 수 
        baskets = {}
        for basket in range(N):
            baskets.update({basket+1:[basket+1]})
        # print(" 바구니 생성 완료")
        for m in range(M):
            i,j = map (int, sys.stdin.readline().split()) # i 번째 바구니와 j번째 바구니의 숫자를 교환한다. 
            # from i to j bucket -> input k
            baskets[i],baskets[j] = baskets[j],baskets[i] 

        else:
            for i in baskets.keys():
                print(baskets[i][0] if len(baskets[i]) !=0 else 0, end =" ",)
class chpater4:
    ########-- Chapter 4.  Array --- #######
    def asignmentCheckIn30Students():
        # student Number
        sNumbers = [sN+1 for sN in range(30)]
        import sys
        for i in range(28):
            check = int(sys.stdin.readline())
            sNumbers.remove(check)
        else:
            for i in sNumbers:
                print(i)
    def modwith42CompareCount():
        import sys


        modArr =[]
        for i in range(10):
            A = int(sys.stdin.readline())
            if A%42 not in modArr:
                modArr.append(A%42)
        print(len(modArr))
    def changingBasketOrder():
        ## N,M 
        import sys 
        N, M = map ( int, sys.stdin.readline().split())
        baskets = [i+1 for i in range(N)] # 바구니 배열 생성 배열안의 원소는 바구니번호이다. 
        # print(baskets)
        for m in range(M):
            i, j =map (int, sys.stdin.readline().split())
            
            ## 바구니 순서 바꾸기 
            # print(i, j)
            # print(baskets[i-1:j])
            baskets[i-1:j]=baskets[i-1:j][::-1] 
            # print("부분결과",baskets[i-1:j])
            # print("전체결과",baskets)
            
            
        
        ## 출력
        for i in baskets:
            print(i, end= " ")
    def manipulateGrade():
        import sys
        N = int(input())
        scores = list(map(int, sys.stdin.readline().split()))
        sumofScores = sum(scores)
        changedGrade = [ float(score/max(scores))*100.0 for score in scores]
        
        print(sum(changedGrade)/len(changedGrade))
    #manipulateGrade()
class chpater5:
    ########-- Chapter 5. String  --- #######
    def stringInputTest():
        import sys 
        
        a = sys.stdin.readline() 
        n = int(sys.stdin.readline())    
        print(a[n-1])
    def stringLengthCheck():
        a = input()
        print(len(a))
    def stringFirstAndEnd():
        N = int(input())
        inputStr = []
        for i in range(N):
            inputStr.append(input())
        for i in inputStr:
            print(i[0], i[-1],sep ="")
    def changeASCIcodefromCharcter():
        inputStr = input()
        print(ord(inputStr))
    def sumNumbers():
        digit= input()
        number =list(input()) 
        number_int = map(int, number)
        print(sum(number_int))
    def findAlphabet():
        stringInputs = str(str(input()))
        # print(list(stringInputs))
        alphabet_lower=[i for i in range(ord('a'),ord('z')+1)]
        result =""
        for i in  alphabet_lower:
            result += str(stringInputs.find(chr(i))) + " "
        result=result.rstrip()
        print(result)
        # re = '1 0 -1 -1 2 -1 -1 -1 -1 4 3 -1 -1 7 5 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1'
        # print(re)
        # print(result == re)
    def QRcodeGen():
        T = int(input())
        result = []
        for i in range(T):
            R, S = map(str,input().split())
            result.append(''.join([i*int(R) for i in list(S)]))
        for i in result : print(i)
    def countingWords():
        stringInputs = list(map( str,input().split()))
        print(len(stringInputs))
    def SangsuCompareNumber():
        inpput = list(map(str,(input().split())))

        numbers =[int(i[::-1]) for i in inpput]
        print(max(numbers))
    def dialPhoneNumbering():
        alphabet_Topper = [ chr(i) for i in range(ord('A'),ord('Z')+1)]
        startNum =0
        phoneDic = {}
        for i in range(10):
            if i == 0:
                # print("0 :")
                phoneDic[i]= ""
            elif i ==1:
                phoneDic[i]= ""
                # print("1 : ")
            elif i ==7 or i ==9:
                phoneDic[i]= alphabet_Topper[startNum:startNum+4]
                # print(i, startNum, alphabet_Topper[startNum:startNum+4])
                startNum += 4
            else:
                phoneDic[i]=alphabet_Topper[startNum:startNum+3]
                # print(i, startNum, alphabet_Topper[startNum:startNum+3])
                startNum +=3
        # print("-"*20)
        phoneDic =  { ''.join(v):k for k,v in phoneDic.items()}
        # print(phoneDic)
        # StringNumber test = WA
        # test key 를 분해 한뒤 각 문자가 어느 key 에 속하는지 알아내는 과정 
        teststr = input()
        
        ## phone number -> time second 
        # 1 -> 2C초, 2 : 3초.. 9 -> 10초 
        time_calc = 0
        for i in teststr:
            for phonestr in phoneDic.keys():
                if i in phonestr:
                    #print(i,phonestr, phoneDic[phonestr])
                    # print(phonestr[phonestr])
                    time_calc += phoneDic[phonestr]+1
        print(time_calc)

class chapter6:

        ########-- Chapter 6. 심화1  --- #######
    def mirrorPrinting():
        
        while True:
            try :
                s = input()
                print(s)
                if len(s)==0 :
                    break
            except EOFError: 
                break
    def SpringImage():
        print("         ,r'\"7")
        print("r`-_   ,'  ,/")
        print(" \\. \". L_r'")
        print("   `~\\/")
        print("      |")
        print("      |")
    def chessCalc():
        import sys 
        n = list(map(int , sys.stdin.readline().split()))
        # 킹:1, 퀸:1 , 룩:2, 비숏:2, 나이트:2, 폰:8 
        chess_dic = { "킹":1, "퀸":1 , "룩":2, "비숏":2, "나이트":2, "폰":8 }
        need = []
        for real, chessRule in zip(n,chess_dic.keys()):
            # print(chessRule, real, chess_dic[chessRule])
            need.append(chess_dic[chessRule]-real)
        for i in need:
            print(i , end = " ")

    def printingStar_7():
        import sys 
        n = int(sys.stdin.readline())
        a= ["*"*(2*n-1-2*(i-n)) if i+1 >n else "*"*(2*i-1)for i in range(n*2+1)]
        #print(a)
        for idx,star in enumerate(a[1:-1]):
            # print(abs(n-1-idx))
            strprint  = " "*abs(n-1-idx)+f"{star :<}".rstrip()
            #print(f"{abs(n-1-idx)}/{len(strprint)}",strprint)
            print(strprint)
    # printingStar_7()
    def 팰린드롬인지확인하기():

        """
        Date : 2024.08.02
        문제:
            알파벳 소문자로만 이루어진 단어가 주어진다. 이때, 이 단어가 팰린드롬인지 아닌지 확인하는 
            프로그램을 작성하시오.
            팰린드롬이란 앞으로 읽을 때와 거꾸로 읽을 때 똑같은 단어를 말한다. 
            level, noon은 팰린드롬이고, baekjoon, online, judge는 팰린드롬이 아니다.
        """
        import sys 
        a = sys.stdin.readline().rstrip()
        reverse_a="".join(list(reversed(a)))
        print(1 if a==reverse_a else 0)

    def 단어공부():
        import sys 
        a = list(sys.stdin.readline().rstrip().lower())
        # print(F.red("".join(a).lower()))
        # print(a.count("a"))
        a_set = set(a)
        # print(f"{a_set}")
        max_count = 0
        result_char = ""
        is_over_2 = 0
        count_array =[]
        ## max가 두개 이상인지 체크 
        for i in a_set:
            count_array.append(a.count(i))
        maz_num = max(count_array)

        if count_array.count(maz_num)>1:
            print("?")
        else:
            for i in a_set:
                if max_count < a.count(i):
                    max_count = a.count(i)
                    result_char = i
            else:
                print(result_char.upper())
    
    def 크로아티아알파벳():
        """
        Date : 2024.08.02-05
        문제:
            예를 들어, ljes=njak은 크로아티아 알파벳 6개(lj, e, š, nj, a, k)로 이루어져 있다. 
            단어가 주어졌을 때, 몇 개의 크로아티아 알파벳으로 이루어져 있는지 출력한다.
            dž는 무조건 하나의 알파벳으로 쓰이고, d와 ž가 분리된 것으로 보지 않는다.
            lj와 nj도 마찬가지이다. 위 목록에 없는 알파벳은 한 글자씩 센다.
        """
        croatia_alphabet = ["c=","c-","dz=","d-","lj","nj","s=","z="]
        example = "ljljes=njak"

        find_index ={}
        for i in croatia_alphabet:
            if i in example:
                find_index[f'{i}']= example.find(i) ## example 에서 몇번재 부터 이게 있는지 
                
                # print(F.red(i),F.yellow(i),end="")
        print(find_index)
        for ch,idx in find_index.items():
            print(ch,idx)
            example.replace(ch,"0"*len(ch))
            print(F.yellow(example))

if __name__ == "__main__":

    while True: 
        print(F.yellow("🔸"*20))
        print(F.blue("🙆🏻‍♀️문제 풀이 시작"))
        
        print(F.yellow("😀 👇👇👇👇인풋을 입력하세요 👇👇👇👇"))
        chapter6.크로아티아알파벳()
        print(F.green("다시 실행하시겠습니니까?(yes =1, no=0): "))
        restart_query = int(sys.stdin.readline())
        if restart_query == 0:
            break        





