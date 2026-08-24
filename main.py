def somar(a, b):
    return a + b

def calculadora():
    print("=== Calculadora Simples ===")
    a = float(input("Digite o valor de a: "))
    b = float(input("Digite o valor de b: "))
    
    resultado = somar(a, b)
    print(f"Resultado da soma: {resultado}")

if __name__ == "__main__":
    calculadora()