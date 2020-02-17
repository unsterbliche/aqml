%pal nprocs 2 end
%maxcore 1000
! b3lyp TIGHTSCF
! cc-pvdz def2/J RIJCOSX
! Opt

%geom
maxiter 60
TolE 1e-4
TolRMSG 2e-3
TolMaxG 3e-3
TolRMSD 2e-2
TolMaxD 3e-2
end

*xyz 0 1
C 0.3198 -0.9516 0.5248
C -0.1505 0.29 0.3459
C -1.5428 0.7314 0.6838
C -2.6462 0.0876 -0.1403
O -2.5002 -0.7944 -0.9801
H -0.3027 -1.7456 0.9266
H -1.7534 0.5359 1.7411
H -1.6193 1.814 0.5324
H -3.6572 0.4729 0.0796
H 1.3381 -1.2068 0.248
H 0.5116 1.0418 -0.0784
*
