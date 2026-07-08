attempts = 0

while True:
    pin_code = int(input("Pin:"))
    attempts += 1
    if pin_code != 4321:
        print("Wrong")
        success = False
    if pin_code == 4321:
        success = True
    if attempts == 1 and success:
        print("Correct! It only took you one single attempt!")
        break
    elif success:
        print(f"Correct! It took you {attempts} attempts")
        break
    