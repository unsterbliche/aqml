#!/usr/bin/env python

import os,sys,re
from ase import Atom, Atoms
import io2
import io2.data as data
from io2.gaussian_reader import GaussianReader as GR0
import ase.data as ad
import numpy as np
import multiprocessing

global dic_sm, atom_symbs, prop_names
dic_sm = {'H':2,'B':2,'C':3,'N':4,'O':3,'F':2, \
          'Si':3,'P':4,'S':3,'Cl':2,'Ge':3,'As':4,\
          'Se':3,'Br':2,'I':2}
atom_symbs = ['C', 'B', 'F', 'I', 'H', 'O', 'N', 'P', \
                  'S', 'Se', 'As', 'Cl', 'Si', 'Ge', 'Br']
prop_names = ['NMR', 'ALPHA', 'MU', 'AE', 'G','U0','U','H', \
              'HOMO','LUMO','GAP', 'IP','EA', 'OMEGA1', \
              'MP','BP']

def is_job_done(f):
    el = file(f).readlines()[-1] # end line
    return 'Normal termination' in el


class GR(object):

    def __init__(self, f, properties=['AE'], unit='kcal', istart=0):

        self.f = f
        self.unit = unit

        assert is_job_done(f), '#ERROR: Gaussian calculation was terminated abnormally?'

        dic = GR0(f, istart=istart)[-1]
        self.coords = dic['Positions']
        self.zs = dic['Atomic_numbers']
        self.atoms = Atoms(self.zs, self.coords)
        self.na = len(self.zs)
        self.sm = dic['Multiplicity']
        self.charge = dic['Charge']
        self.dic = dic

        uo = io2.Units()
        self.uo = uo
        self.const = {'kcal': uo.h2kc, 'kj': uo.h2kj, 'h': 1.0, \
                 'ev': uo.h2e, }[unit.lower()]

        if type(properties) is str: properties = [ properties.upper(), ]

        # visited or not?
        imo, ie, ithermo, imu, ipolar, inmr, iforce, ipop = 0, 0, 0, 0, 0, 0, 0, 0
        ys = []
        visited = []
        for property_i in properties:
            pname = property_i.upper()
            if pname in ['HOMO','LUMO','GAP']:
                if not imo:
                    imo = 1
                    self.get_mo_energy()
            elif pname in ['E', 'AE', 'EE', 'EN' ]:
                if not ie:
                    ie = 1
                    self.get_energy(etype=pname)
            elif pname in ['HF', 'MP2', 'CCSD(T)', ]:
                if pname not in visited:
                    self.get_ei(pname)
                    visited.append( pname )
            elif pname in ['U0', 'U', 'H', 'G', 'ZPE', 'ZPVE']:
                if not ithermo:
                    ithermo = 1
                    self.get_thermo()
            elif pname in ['MU',]:
                if not imu:
                    imu = 1
                    self.get_dipole_moment()
            elif pname in ['ALPHA',]:
                if not ipolar:
                    ipolar = 1
                    self.get_polarizability()
            elif pname in ['NMR',]:
                if not inmr:
                    inmr = 1
                    self.get_nmr()
            elif pname in ['FORCE',]:
                if not iforce:
                    iforce = 1
                    self.get_force()
            elif pname in ['POPULATION',]:
                if not ipop:
                    ipop = 1
                    self.get_mulliken_population()
            else:
                raise '#ERROR:'
            ys.append( self.dic[ property_i ] )
	    self.properties = ys

    def update_dic(self, ss1, ss2):
        for i, s1 in enumerate(ss1):
            self.dic[s1] = ss2[i]

    def get_ei(self, ein): # `ein -- energy_i name, i.e., HF, MP2, CCSD(T)
        self.update_dic([ein, ], [ self.dic[ein]*self.const, ])

    def get_energy(self,etype='E'):
        f = self.f
        # first read method
        cmd1 = "grep -n ' # ' %s | head -n 1"%f
        s0 = os.popen(cmd1).read().strip().split(':')
        #print 'f,s0 = ',f,s0;
        n0 = int(s0[0]); s0_1 = s0[1]

        # in case the command line has two many user-specified keywords
        # so that it spans more than 1 line
        s0u = s0_1
        while True:
            cmd1_i = "sed -n '%sp' %s"%(n0+1,f)
            s0_i = os.popen(cmd1_i).read().strip()
            if set([ si for si in s0_i ]) != set(['-',]):
                s0u += s0_i; n0 += 1
            else:
                break

        s1 = s0u.split()
        #print s1
        ns1 = len(s1)
        method1 = None
        isGn = False
        basis = ''
        # for MY calculation, the command line always goes like "# G4MP2"
        if ns1 == 2 and (s1[1][0].upper() == 'G'):
            isGn = True
            method1 = s1[1]
        else:
            # assume this is a normal method with "/" seperating `qcl and
            # `basis, e.g., B3LYP/6-31G(d,p)'
            for sj in s1:
                if '/' in sj:
                    #print 'Yeah, sj = ',sj
                    cont1 = sj.split('/')
                    method1 = cont1[0]
                    basis1 = cont1[1]
                    ss0 = ['-','+','+','(',')',',']
                    ss1 = ['\-','\+','\+','(',')',',']
                    ss2 = ['','j','j','','','']
                    for js,sj in enumerate(ss1):
                        if ss0[js] in basis1:
                            cmd = "echo '%s' | sed -n 's/%s/%s/p'"%(basis1, sj, ss2[js])
                            basis1 = os.popen(cmd).read().strip()
                    break

        if method1 is None:
            print ' #ERROR: method cannot be retrieved??'
            sys.exit(3)
        #else:
        #    if 'maxcyc' in method1:
        #        # e.g.,  "# uqcisd(t)(maxcyc=100)/6-311++g(d,p)"
        #        idx0 = method1.index('(max')
        #        method1 = method1[:idx0]

        # now read energy
        m1U = method1.upper(); #print ' ** meth = ', m1U
        if m1U in ['B3LYP', 'RB3LYP', 'UB3LYP']:
            cmd2 = "grep 'E([RU]B3LYP) =' %s | tail -n 1 | awk '{print $5}'"%f #out
            # e.g.,
            #  SCF Done:  E(RB3LYP) =  -40.5236797399     A.U. after   10 cycles
            #print cmd2
            E_str = os.popen(cmd2).read().strip()
        elif m1U in ['CCSD(T)', 'QCISD(T)', 'UCCSD(T)', 'UQCISD(T)']:
            m1Uu = {'UQCISD(T)':'QCISD(T)', 'QCISD(T)':'QCISD(T)', 'UCCSD(T)':'CCSD(T)', 'CCSD(T)':'CCSD(T)'}[m1U]
            cmd2 = "grep '^ %s=' %s"%(m1Uu,f); #print cmd2
            # e.g.,
            #  QCISD(T)= -0.11358793642D+03
            E_str = os.popen(cmd2).read().strip().split('\n')[0].split()[-1]
        elif m1U in ['HF','RHF','UHF',]:
            cmd2 = "grep 'E([RU]HF) =' %s | tail -n 1"%f
            E_str = os.popen(cmd2).read().strip().split('=')[1].split()[0]
        elif m1U in ['MP2','RMP2','UMP2',]:
            cmd2 = "grep 'EUMP2 = ' %s | tail -n 1"%f
            E_str = os.popen(cmd2).read().strip().split()[-1]
        else:
            print '#ERROR: not implemented yet'; sys.exit(3)

        if 'D' in E_str:
            E = eval( 'E'.join( E_str.split('D') ) )
        else:
            E = eval( E_str )

        self.E = E*self.const


        atoms = self.atoms
        qcl = method1 + basis1
        self.qcl = qcl
        #print '  -- qcl = ', qcl
        if etype == 'AE':
            ea_refs = data.retrieve_esref( qcl.lower() )
            E0 = 0.
            symbs = [ ai.symbol for ai in atoms ]
            for si in symbs: E0 += ea_refs[si][0]
            self.AE = (E - E0)*self.const
            self.update_dic( ['qcl','AE'], [self.qcl, self.AE] )
        elif etype == 'EE': # electronic energy
            cmd1 = "awk '/nuclear repulsion energy/{print NR}' %s | tail -n 1"%f
            En = eval( io2.cmdout2(cmd1) ) * self.const
            Ee = E - En
            self.En = En
            self.Ee = Ee
            self.update_dic( ['qcl','E','EN','EE'], [self.qcl,self.E,En,Ee] )
        else:
            self.update_dic( ['qcl','E',], [self.qcl, self.E] )


    def get_mo_energy(self):
        """
        get HOMO, LUMO and their gap
        """
        f = self.f
        cmd1 = "awk '/^ The electronic state is/{print NR}' %s | tail -n 1"%f
        Ln1 = int(io2.cmdout2(cmd1)) + 1
        cmd2 = "awk '/^          Condensed to atoms \(all electrons\)/{print NR}' %s | tail -n 1"%f
        Ln2 = int(io2.cmdout2(cmd2)) - 1
        cmd = "sed -n '%d,%dp' %s | grep Beta"%(Ln1,Ln2,f)
        cont0 = io2.cmdout2(cmd)
        if cont0 != '':
            print ' Alpha & Beta spins are both involved, spin polarized??'
            sys.exit(2)
        else:
            cmd = "sed -n '%d,%dp' %s | grep ' Alpha virt. eigenvalues --' | head -n 1"%(Ln1,Ln2,f)
            ct = io2.cmdout2(cmd);
            self.lumo = eval( ct.split()[-5] ) * self.uo.h2e
            cmd = "sed -n '%d,%dp' %s | grep ' Alpha  occ. eigenvalues --' | tail -1"%(Ln1,Ln2,f)
            ct = io2.cmdout2(cmd)
            self.homo = eval( ct.split()[-1] ) * self.uo.h2e
            #iseed = debug(iseed)
            self.gap = self.lumo - self.homo

            self.update_dic(['homo','lumo','gap'], [self.homo, self.lumo, self.gap])
            self.update_dic(['HOMO','LUMO','GAP'], [self.homo, self.lumo, self.gap])

    def get_thermo(self, scale_factor=0.965):
        """
        for DFT, the `scale_factor is 0.965
        """
        f = self.f
        cmd = "grep '^ Freq' %s"%f
        # data in lines below could be retrieved together
        #
        # Sum of electronic and zero-point Energies=           -174.095490
        # Sum of electronic and thermal Energies=              -174.091365
        # Sum of electronic and thermal Enthalpies=            -174.090421
        # Sum of electronic and thermal Free Energies=         -174.122620
        conts = io2.cmdout(cmd)
        assert conts != [], '#ERROR: no thermochem was done!'
        if not isGn:
            cmd = "awk '/^ Sum of electronic and/{print $NF}' %s"%f
            U0, U, H, G = np.array( io2.cmdout(cmd) ).astype(np.float) * self.const
            self.U0, self.U, self.H, self.G  = U0, U, H, G

            cmd = "awk '/^ Zero-point correction=/{print $3}' %s"%f
            zpe = eval(io.cmdout(cmd)[0]) * self.const # the last two entries are "0.81475823 Hartree/atom"
            self.zpe = self.zpve = zpe
        else:
            print '#ERROR: cannot handle output of Compositional method like G4MP2 yet!'
            sys.exit(2)
        E_ = U0 - zpe
        #assert abs(E_ - E) < 0.0001, '#ERROR: '

        # people usually scale ZPE by a factor, for B3LYP, it's 0.965??
        U0c = E_ + scale_factor*zpe
        self.U0c = U0c
        self.update_dic(['U0', 'U0c', 'U', 'H', 'G'], [U0, U0c, U, H, G])

    def get_dipole_moment(self):
        cmd = "grep -A1 ' Dipole moment (field-independent basis, Debye):' %s | tail -1 | awk '{print $NF}'"%self.f
        self.mu = eval( io2.cmdout2(cmd) )
        self.update_dic(['MU', 'DIPOLE'], [self.mu, self.mu])

    def get_polarizability(self):
        cmd = "awk '/Isotropic polarizability/{print $6}' %s"%self.f
        #print cmd
        try:
            self.alpha = eval( io2.cmdout2(cmd) )
            self.update_dic(['ALPHA',], [self.alpha,])
        except:
            print ' * WARNING: no Isotropic polarizability found'

    def get_nmr(self):
        cmd = "awk '/  Isotropic =  /{print $5}' %s"%self.f
        vals = io2.cmdout(cmd)
        self.nmr = [ eval(val) for val in vals ]
        self.update_dic(['NMR',], [self.nmr,])

    def get_mulliken_population(self):
        # note that the output Mulliken charge starting line may be different
        # for different versions of Gaussian, i.e., with or without `atomic` in between
        # "Mullike" and "charges:", so a regular expression is used
        cmd1 = "awk '/^ Mulliken [a-zA-Z]*\s?charges:/{print NR}' %s | tail -1"%self.f
        #print cmd1
        Ln1 = int(io2.cmdout2(cmd1)) + 2
        cmd2 = "awk '/^ Sum of Mulliken [a-zA-Z]*\s?charges =/{print NR}' %s | tail -1"%self.f
        Ln2 = int(io2.cmdout2(cmd2)) - 1
        cmd = "sed -n '%d,%dp' %s"%(Ln1,Ln2,self.f)
        cs = io2.cmdout2(cmd).split('\n')
        pops = [ eval(ci.split()[2]) for ci in cs ]
        #pops = np.array(vals)
        self.populations = pops
        self.update_dic(['POPULATION',], [self.populations,])

    def get_force(self):
        iou = io2.Units()
        const = iou.h2e / iou.b2a # from hartree/bohr to eV/A
        #cmd = "grep '^\s*[XYZ][0-9]*   ' %s | awk '{print $3}'"%self.f #
        cmd1 = "awk '/^ Variable       Old X    -DE/{print NR}' %s | tail -1"%self.f
        Ln1 = int(io2.cmdout2(cmd1)) + 2
        cmd2 = "awk '/^         Item               Value     Threshold  Converged/{print NR}' %s | tail -1"%self.f
        Ln2 = int(io2.cmdout2(cmd2)) - 1
        cmd = "sed -n '%d,%dp' %s"%(Ln1,Ln2,self.f)
        #print cmd
        cs = io2.cmdout2(cmd).split('\n')
        vals = [ eval(ci.split()[2]) for ci in cs ]
        #print vals
        #print len(vals)
        forces = np.array(vals).reshape((self.na, 3)) * const
        #abs_forces = np.linalg.norm( forces, axis=1 )
        #self.forces = abs_forces[:, np.newaxis]
        self.forces = forces
        self.update_dic(['FORCE',], [self.forces,])


class GRs(object):

    def __init__(self, fs, properties=['AE'], unit='kcal', write_Y=False, nproc=1, istart=0):

        self.n = len(fs)
        typeP = type(properties)
        if typeP is str:
            properties = [ properties.upper(), ]
        elif typeP is list:
            properties = [ prop.upper() for prop in properties ]
        else:
            raise '#ERROR,'
        npr = len(properties)
        istats = [] # is_local_property = False
        for propi in properties:
            istat = False # assume global property
            if propi in ['POPULATION','NMR']:
                istat = True
            istats.append( istat )

        if nproc == 1:
            self.objs = []
            for i,f in enumerate(fs):
                #print i+1, f
                ipt = [ f, properties, unit, istart ]
                self.objs.append( self.processInput(ipt) )
        else:
            pool = multiprocessing.Pool(processes=nproc)
            ipts = [ [ fi, properties, unit ] for fi in fs ]
            self.objs = pool.map(self.processInput, ipts)

        ys = []
        #print ' - npr = ', npr
        for ipr in range(npr):
            ysi = []
            for obj in self.objs:
                #print ' - obj.properties = ', obj.properties
                yi = obj.properties[ipr]; #print ' ysi = ', ysi
                if istats[ipr]: # atomic property, e.g., NMR shifts
                    ysi += yi
                else:
                    ysi.append( yi )
            ys.append( ysi )
        #print ys
        self.dic = dict( zip(properties, ys) )
        if write_Y:
            for ipr in range(npr):
                np.savetxt('%s.dat'%properties[ipr], ys[ipr], fmt='%.2f')

    def processInput(self, ipt):
        f, properties, unit, istart = ipt
        obj = GR(f, properties=properties, unit=unit, istart=istart)
        return obj

    def get_statistics(self):
        """
        `zs, `nas, `nhass, `coords, etc
        """
        zs = []
        zsr = []
        nas = []
        nhass = []
        zsu = set([])
        coords = []
        for i in range(self.n):
            obj_i = self.objs[i]
            coords.append( obj_i.coords )
            zsi = obj_i.zs
            nhass.append( (np.array(zsi)>1).sum() )
            nas.append( len(zsi) )
            zsu.update( zsi )
            zsr += list(zsi)
            zs.append( zsi )
        zsu = list(zsu)
        nzu = len(zsu)
        zsu.sort()
        nzs = np.zeros((self.n, nzu), np.int32)
        for i in range(self.n):
            for iz in range(nzu):
                istats = np.array(zs[i]) == zsu[iz]
                nzs[i,iz] = np.sum(istats)
        self.nzs = nzs
        self.zsu = zsu
        self.zs = zs
        self.zsr = np.array(zsr,np.int32)
        self.nas = np.array(nas,np.int32)
        self.nhass = np.array(nhass,np.int32)
        self.coords = coords


def get_line_number(cmd):
    return int(io2.cmdout2(cmd).split(':')[0])

def read_coords(f):
    lines = file(f).readlines()
    cmd0 = "grep -n ' Input orientation:' %s | tail -1"%f
    #cmd0 = "grep -n ' Standard orientation:' %s | tail -1"%f
    #print cmd0
    ln = get_line_number(cmd0) + 5
    zs = []; coords = []
    while 1:
        l = lines[ln-1].strip()
        if l[:10] == '-'*10: break
        ia,zi,_,x,y,z = l.split()
        zs.append(int(zi))
        coords.append([eval(xi) for xi in [x,y,z]])
        ln += 1
    return zs,coords

    obsolete="""#cmd1 = "grep -n '    Distance matrix (angstroms):' %s | tail -1"%f
    cmd1 = "grep -n ' Rotational constants (GHZ):' %s"%f
    #print cmd1
    ln1s = get_line_number(cmd1);
    if type(ln1s) is int: ln1s = [ln1s,]
    nnl = len(ln1s)
    fconts = file(f).readlines()
    ln1_found = False
    for jn in range(1,nnl+1):
        if fconts[ ln1s[-jn]-2 ].strip() == '-'*69:
            ln1 = ln1s[-jn] - 2
            ln1_found = True
            break

    if not ln1_found:
        print ' #ERROR: `ln1 not assigned!!'"""

def get_cf_and_chg(f):
    """ cf: chemical formula
        chg: charge """
    cmdi = "grep Stoichiometry %s | tail -1"%f
    ct = io2.cmdout2(cmdi)
    info = ct.split()[-1]
    if ('(' in info) and (info[-1] == ')'):
        # charged mol
        cf, c0_ = info.split('(') # cf: chemical formula;
        if c0_[-2] == '-':
            chg = -int(c0_[:-2]) # negatively charged
        elif c0_[-2] == '+':
            chg = int(c0_[:-2]) # positively charged
        else:
            #print 'c0_ = ', c0_, ', ct = ', ct
            #sys.exit(2)
            chg = 0 # spin-polarized case, e.g., C4H9O(2)
    else:
        chg = 0
        cf = info
    return cf, chg

def get_spin(f):
    cmdi = "grep 'Multiplicity =' %s | tail -1"%f
    ct = cmdout2(cmdi).split()
    chg = int(ct[2]); sm = int(ct[-1])
    return sm, chg


if __name__ == "__main__":
    import sys
    import stropr as so

    args = sys.argv[1:]

    idx = 0
    keys=['-p','-properties']; hask,s,idx = so.parser(args,keys,'E',idx)
    assert hask
    props = s.split(',')

    fs = args[idx:]

    #test
    obj = GRs(fs, properties=props)
    for propi in props:
        for (f,p) in zip(fs,obj.dic[propi]):
            print f,p


