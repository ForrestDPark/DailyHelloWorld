
class Problem_02:
    def odd_even_determine():
        import sys;print( '짝수입니다' if int(sys.stdin.readline().rstrip()) %2 ==0 else '홀수입니다')
            
if __name__ == "__main__":

    while True: 
        import sys
        
        print("숫자를 입력하세요 :")
        Problem_02.odd_even_determine()
        print("다시 실행하시겠습니니까?(yes =1, no=0): ")
        restart_query = int(sys.stdin.readline())
        if restart_query == 0:
            break        
