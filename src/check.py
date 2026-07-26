import sys
import lxml
import pandas
import pyarrow
import duckdb
import lifelines
import statsmodels

print("Python:", sys.version)
print("lxml:", lxml.__version__)
print("pandas:", pandas.__version__)
print("pyarrow:", pyarrow.__version__)
print("duckdb:", duckdb.__version__)
print("lifelines:", lifelines.__version__)
print("statsmodels:", statsmodels.__version__)

print("\nEnvironment verification passed.")