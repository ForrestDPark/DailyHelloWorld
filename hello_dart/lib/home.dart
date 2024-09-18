import 'package:flutter/material.dart';

class Home extends StatelessWidget {
  const Home({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(),
      body: const Center(
        child: Text("""
        2024.09.18. Wed PM 03:17 
        hello world
          - button 생성해보자...
          - Fultter review 해보자  """),
        // 내일 간수치 검사. 더높아지면 ct 복부 찍을 수도 있음. 
        // 조형 제가 들어가야해서 6시간 금식. 
        // 아침먹고 금식 후 피검사 보고 금식 해제 
      ),
    );
  }
}