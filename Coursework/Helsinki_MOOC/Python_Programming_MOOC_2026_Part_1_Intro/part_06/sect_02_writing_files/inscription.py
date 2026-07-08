# Write your solution here

user_name = str(input("Whom should I sign this to: "))
user_filename = str(input("Where shall i save it: "))

with open(user_filename, "w") as user_file:
    user_file.write(f"Hi {user_name}, we hope you enjoy learning Python with us! Best, Mooc.fi Team")