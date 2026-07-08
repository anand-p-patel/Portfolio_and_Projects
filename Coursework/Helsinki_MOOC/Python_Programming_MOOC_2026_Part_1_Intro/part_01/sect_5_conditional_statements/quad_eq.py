# Write your solution here
# Let's take the square root of math-module in use
from math import sqrt

# Note that the square root can also be calculated using power.
# sqrt(9) is equivalent to 9 ** 0.5
a_var = float(input("Value of a:"))
b_var = float(input("Value of b:"))
c_var = float(input("Value of c:"))

root1 = (-b_var + sqrt((b_var**2)-4*a_var*c_var)) / (2*a_var)
root2 = (-b_var - sqrt((b_var**2)-4*a_var*c_var)) / (2*a_var)

print(f"The roots are {root1} and {root2}")