# Write your solution here

user_choice = int(input("Layers: "))
characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

left = ""
right = ""

i = user_choice - 1
j = 2*user_choice - 1

while i >= 1:
    left = left + characters[i]
    right = characters[i] + right
    j -= 2
    print(left+characters[i]*j+right)
    i -= 1
while i <= user_choice - 1:
    print(left+characters[i]*j+right)
    left = left[:-1]
    right = right[1:]
    j += 2
    i += 1