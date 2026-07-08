# write your solution here
user_choice = str(input("Write text: "))
with open("wordlist.txt") as file:
    wordlist_list = []
    for line in file:
        wordlist_list.append(line.strip().lower())

user_no_spaces = user_choice.split(' ')
final = ''
for text_word in user_no_spaces:
    if text_word.lower() in wordlist_list:
        final += text_word + " "
    else:
        final += "*" + text_word + "* "

print(final.strip())
