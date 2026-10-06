# C port of simvec._dust_lvl_s. Same signature, same answers, C loops.
#
# Layout: two flattened (kind,id) pair lists per cell, built ONCE per tables
# object and cached by id (with a strong ref, so no id-reuse aliasing):
#   F15: fifteen-sources -> any one lit returns 15. kind 0=pbs, 1=tl, 2=ron.
#        (d_bt/d_bp/d_rblk stay scalar per-cell fields, exactly as Python.)
#   LVL: level sources -> max. kind 1 reads con[m], else pw[m]-1.
# d_lev names stay Python (lever-adjacent dust is rare; dict.get there).
# State (pw/pbs/tl/ron/con) arrives as the live bytearrays and is viewed
# zero-copy; re-bound only when object identity changes (i.e. once/vector).
# Order-independence is physics, not an assumption: 15-wins plus max, so
# the merged loops answer exactly what the per-class loops answer.
from array import array


cdef class Tables:
    cdef object src
    cdef int nid
    cdef object _bt_a, _bp_a, _rb_a
    cdef int[:] d_bt, d_bp
    cdef unsigned char[:] d_rblk
    cdef object _o15_a, _i15_a, _olv_a, _ilv_a
    cdef int[:] o15, i15, olv, ilv
    cdef object _s15_a, _svl_a
    cdef int[:] s15, svl
    cdef list lev
    cdef object _pw_o, _pbs_o, _tl_o, _ron_o, _con_o
    cdef unsigned char[:] pw, pbs, tl, ron, con

    def __init__(self, st, int nid):
        self.src = st
        self.nid = nid
        self._bt_a = array('i', st['d_bt'])
        self._bp_a = array('i', st['d_bp'])
        self._rb_a = bytearray(st['d_rblk'])
        self.d_bt = self._bt_a
        self.d_bp = self._bp_a
        self.d_rblk = self._rb_a
        o15 = array('i')
        i15 = array('i')
        olv = array('i')
        ilv = array('i')
        lev = [()] * nid
        dcob = st['d_cob']
        dtor = st['d_torch']
        drep = st['d_rep']
        ddus = st['d_dust']
        dcom = st['d_comp']
        dcup = st['d_cup']
        dcdn = st['d_cdn']
        dlev = st['d_lev']
        for c in range(nid):
            for m in dcob[c]:
                o15.append(0)
                i15.append(m)
            for m in dtor[c]:
                o15.append(1)
                i15.append(m)
            for m in drep[c]:
                o15.append(2)
                i15.append(m)
            for m in ddus[c]:
                olv.append(0)
                ilv.append(m)
            for m in dcom[c]:
                olv.append(1)
                ilv.append(m)
            for m in dcup[c]:
                olv.append(2)
                ilv.append(m)
            for m in dcdn[c]:
                olv.append(3)
                ilv.append(m)
            # end marker: reuse o15/olv length prefix per cell via second pass
            lev[c] = tuple(dlev[c])
        # cell ranges: rebuild by counting per cell (second pass over lists)
        self._o15_a = o15
        self._i15_a = i15
        self._olv_a = olv
        self._ilv_a = ilv
        self.o15 = o15
        self.i15 = i15
        self.olv = olv
        self.ilv = ilv
        self.lev = lev
        # per-cell start/end into the flat lists
        s15 = array('i', [0]) * (nid + 1)
        svl = array('i', [0]) * (nid + 1)
        n15 = nvl = 0
        for c in range(nid):
            n15 += len(dcob[c]) + len(dtor[c]) + len(drep[c])
            nvl += len(ddus[c]) + len(dcom[c]) + len(dcup[c]) + len(dcdn[c])
            s15[c + 1] = n15
            svl[c + 1] = nvl
        self._s15_a = s15
        self._svl_a = svl
        self.s15 = s15
        self.svl = svl

    cdef void bind(self, pw, pbs, tl, ron, con):
        if pw is not self._pw_o:
            self._pw_o = pw
            self.pw = pw
        if pbs is not self._pbs_o:
            self._pbs_o = pbs
            self.pbs = pbs
        if tl is not self._tl_o:
            self._tl_o = tl
            self.tl = tl
        if ron is not self._ron_o:
            self._ron_o = ron
            self.ron = ron
        if con is not self._con_o:
            self._con_o = con
            self.con = con

    cdef int level(self, int c, dict vec):
        cdef int t = self.d_bt[c]
        if t >= 0 and self.tl[t]:
            return 15
        cdef int p = self.d_bp[c]
        if p >= 0 and self.pbs[p]:
            return 15
        if self.d_rblk[c]:
            return 15
        cdef int s = self.s15[c], e = self.s15[c + 1], k, m
        cdef int[:] ko = self.o15, io = self.i15
        for k in range(s, e):
            m = io[k]
            if ko[k] == 0:
                if self.pbs[m]:
                    return 15
            elif ko[k] == 1:
                if self.tl[m]:
                    return 15
            elif self.ron[m]:
                return 15
        for nm in self.lev[c]:
            if vec.get(nm, False):
                return 15
        cdef int lv = 0, x
        s = self.svl[c]
        e = self.svl[c + 1]
        cdef int[:] kw = self.olv, iw = self.ilv
        for k in range(s, e):
            m = iw[k]
            if kw[k] == 1:
                x = self.con[m]
            else:
                x = self.pw[m] - 1
            if x > lv:
                lv = x
        return lv


cdef dict _CACHE = {}


cdef Tables _for_st(dict st):
    cdef unsigned long long key = id(st)
    cdef Tables t = _CACHE.get(key)
    if t is not None and t.src is st:
        return t
    t = Tables(st, len(st['d_bt']))
    _CACHE[key] = t
    return t


cpdef int dust_lvl_c(int c, dict st, pw, pbs, tl, ron, con, dict vec):
    """Drop-in for simvec._dust_lvl_s (same args, same return)."""
    cdef Tables T = _for_st(st)
    T.bind(pw, pbs, tl, ron, con)
    return T.level(c, vec)
