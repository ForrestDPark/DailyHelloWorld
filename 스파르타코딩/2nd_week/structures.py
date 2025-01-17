class F:
    ### Functions ### 
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
    def b(str):print( F.colored_text(str,'blue'))
    def y(str):print( F.colored_text(str,'yellow'))
    def r(str):print( F.colored_text(str,'red'))
    def g(str):print( F.colored_text(str,'green'))


class ListNode: 
    
    def __init__(self, val = 0, next = None):
        self.val = val
        self.next = next
        F.b(f"   - ⭐️ ListNode({val})실행  : [결과 ({self.val}, {self.next})]")
    def __str__(self):
        return f"({self.val}, {self.next})"

class LinkedList:
    def __init__(self):
        self.head = None
        F.g(f"⭐️ LinkedList() 실행 [head : {self.head}]")
        
    def append(self,val):
        F.r(f"\n 👉LinkedList.append({val}) 실행 : LinkedList 끝 노드에 {val}을 추가합니다.")
        if not self.head:
            F.y(f"   - 기존 헤드 값 {self.head}. =>  head에  {val} 삽입.")
            self.head = ListNode(val,None)
            # print(f"\t self.head:({self.head.val} , {self.head.next})")
            return 

        node = self.head
        F.y(f"    :: 현재 LinkedList 상태 {node} ::")
        step = 0
        F.g(f"       •STEP({step})-> node.next 없음" if not node.next else "  🔸 insert 위해 끝 node 가기 START")
        while node.next:
            if  node.next:
                F.g(f"      •STEP({step})-> node.next 값{node.next} ")
            node = node.next
            step +=1
        F.y(f"   - 끝노드[{node.val},{node.next}]도착!! 다음 노드에 {val} 추가한 결과↓↓↓↓")
        node.next = ListNode(val,None)
        
        ## print(ln) 연결 구조 시각화
        result = []
        node = self.head
        while node:
          result.append(str(node.val))
          node = node.next
        F.y(f"     ::APPEND 후 최종 LinkedList 상태 { ' -> '.join(result)}")
    
    def __str__(self):
        ## print(ln) 연결 구조 시각화
        result = []
        node = self.head
        while node:
          result.append(str(node.val))
          node = node.next
        return " -> ".join(result)
    

class Node:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class Stack:
    def __init__(self):
        self.top = None

    def push(self, value):
        self.top = Node(value, self.top)

    def pop(self):
        if self.top is None:
            return None

        node = self.top
        self.top = self.top.next

        return node.val

    def is_empty(self):
        return self.top is None
    
    


class Queue:
    def __init__(self):
        ## 가장 앞에 있는 녀석 front 
        self.front = None
    
    ## LL 의 node 활용 하여 구현 
    def push(self, value):
        ## push 할때 self 의 front 가 비어있는지 확인하는게 중요
        if not self.front: # 비어있는 경우 
            self.front = Node(value) ## 노드를 집어넣어주고 끝
            return
        ## 뒤에다 하나씩 붙여 나가야한다. 헤드에서 시작해서 제일 뒤로간다. 
        ## 앞에 있는 녀석 설정 
        node = self.front
        while node.next: ## 순회 시작
            node = node.next
        ## 제일끝으로 왔다. 
        node.next = Node(value) ## 끝에 노드를 넣은후 가리킴 
        
    
    ## front 를 꺼낸뒤 없에고 다음 노드를 front 로 지정 한다. 
    def pop(self):
        ## 꺼낼려고 하는데 아무것도 없을 경우 
        if not self.front:
            return None
        ## 노드가 있을때 맨 앞에 있는걸 node 로 지정 
        node = self.front
        
        ## 지금 바라보고잇는 녀석의 다음녀석을 front 로 지정해준다. 
        self.front = self.front.next
        return node.val
    
    ## self 의 front 가 None 이면 비어있다.
    def is_empty(self):
        return self.front is None