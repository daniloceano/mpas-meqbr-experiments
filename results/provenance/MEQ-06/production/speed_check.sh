R=/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meq06_production/run
stat -c '%Y %n' $R/history.2021-1[01]-*.nc $R/history.2021-12-01_00.00.00.nc | sort -n | awk '{t=$1; n=$2; sub(/.*history\./,"",n); d=substr(n,1,10); if(p){dt=t-p; s[d]+=dt; c[d]++}; p=t} END{for(k in s) printf "%s %.0f\n", k, s[k]/c[k]}' | sort
ps -eo pcpu,user,comm --sort=-pcpu | grep -v atmosphere_mod | head -6
