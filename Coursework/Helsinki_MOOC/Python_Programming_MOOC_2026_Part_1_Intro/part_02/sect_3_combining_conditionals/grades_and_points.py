# Write your solution here
#define user input
user_points = int(input("How many points [0-100]:"))

#conditional grade checks
if user_points > 100:
    print("Grade: impossible!")
elif user_points >= 90 and user_points <= 100:
    print("Grade: 5")
elif user_points < 90 and user_points >= 80:
    print("Grade: 4")
elif user_points < 80 and user_points >= 70:
    print("Grade: 3")
elif user_points < 70 and user_points >= 60:
    print("Grade: 2")
elif user_points < 60 and user_points >= 50:
    print("Grade: 1")
elif user_points < 50 and user_points >= 0:
    print("Grade: fail")
else:
    print("impossible!")
