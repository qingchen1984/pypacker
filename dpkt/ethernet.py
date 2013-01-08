# $Id: ethernet.py 65 2010-03-26 02:53:51Z dugsong $

"""Ethernet II, LLC (802.3+802.2), LLC/SNAP, and Novell raw 802.3,
with automatic 802.1q, MPLS, PPPoE, and Cisco ISL decapsulation."""

import struct
import copy
from . import dpkt, stp

ETH_CRC_LEN	= 4
ETH_HDR_LEN	= 14

ETH_LEN_MIN	= 64		# minimum frame length with CRC
ETH_LEN_MAX	= 1518		# maximum frame length with CRC

ETH_MTU		= (ETH_LEN_MAX - ETH_HDR_LEN - ETH_CRC_LEN)
ETH_MIN		= (ETH_LEN_MIN - ETH_HDR_LEN - ETH_CRC_LEN)

# Ethernet payload types - http://standards.ieee.org/regauth/ethertype
ETH_TYPE_PUP		= 0x0200	# PUP protocol
ETH_TYPE_IP		= 0x0800	# IP protocol
ETH_TYPE_ARP		= 0x0806	# address resolution protocol
ETH_TYPE_CDP		= 0x2000	# Cisco Discovery Protocol
ETH_TYPE_DTP		= 0x2004	# Cisco Dynamic Trunking Protocol
ETH_TYPE_REVARP		= 0x8035	# reverse addr resolution protocol
ETH_TYPE_8021Q		= 0x8100	# IEEE 802.1Q VLAN tagging
ETH_TYPE_IPX		= 0x8137	# Internetwork Packet Exchange
ETH_TYPE_IP6		= 0x86DD	# IPv6 protocol
ETH_TYPE_PPP		= 0x880B	# PPP
ETH_TYPE_MPLS		= 0x8847	# MPLS
ETH_TYPE_MPLS_MCAST	= 0x8848	# MPLS Multicast
ETH_TYPE_PPPoE_DISC	= 0x8863	# PPP Over Ethernet Discovery Stage
ETH_TYPE_PPPoE		= 0x8864	# PPP Over Ethernet Session Stage
ETH_TYPE_LLDP		= 0x88CC	#Link Layer Discovery Protocol

# MPLS label stack fields
MPLS_LABEL_MASK	= 0xfffff000
MPLS_QOS_MASK	= 0x00000e00
MPLS_TTL_MASK	= 0x000000ff
MPLS_LABEL_SHIFT= 12
MPLS_QOS_SHIFT	= 9
MPLS_TTL_SHIFT	= 0
MPLS_STACK_BOTTOM=0x0100

# TODO: add option fields

class Ethernet(dpkt.Packet):
	__hdr__ = (
		('dst', '6s', ''),
		('src', '6s', ''),
		('vlan', '>H', None),
		('type', 'H', ETH_TYPE_IP)
		)
	__chg__ = [
		["dst2", "6s", ""]
		]
	_typesw = {}

	def _unpack_data(self, buf):
		print("Ethernet _unpack_data")
		if self.type == ETH_TYPE_8021Q:
			print("ETH_TYPE_8021Q")
			self.tag, self.type = struct.unpack('>HH', buf[:4])
			buf = buf[4:]
		elif self.type == ETH_TYPE_MPLS or \
			self.type == ETH_TYPE_MPLS_MCAST:
			print("ETH_TYPE_MPLS ETH_TYPE_MPLS_MCAST")
			# XXX - skip labels (max # of labels is undefined, just use 24)
			self.labels = []
			for i in range(24):
				entry = struct.unpack('>I', buf[i*4:i*4+4])[0]
				label = ((entry & MPLS_LABEL_MASK) >> MPLS_LABEL_SHIFT, \
						 (entry & MPLS_QOS_MASK) >> MPLS_QOS_SHIFT, \
						 (entry & MPLS_TTL_MASK) >> MPLS_TTL_SHIFT)
				self.labels.append(label)
				if entry & MPLS_STACK_BOTTOM:
					break
			self.type = ETH_TYPE_IP
			buf = buf[(i + 1) * 4:]
		try:
			print("Ethernet setattr")
		# TODO: separate function for post-unpack
			self.data = self._typesw[self.type](buf)
			setattr(self, self.data.__class__.__name__.lower(), self.data)
		except (KeyError, dpkt.UnpackError):
			print("Ethernet setattr except")
			self.data = buf

	def unpack(self, buf):
		print("Ethernet unpack")
		# TODO: we need to check for VLAN here (0x8100) and THEN call super implementation
		vlan_tmp = struct.unpack('>BB', self.data[13:14])[0]
		# TODO: test this
		if vlan_tmp == '\x81\x00'
			self.__hdr_defaults__["vlan"] = ''

		dpkt.Packet.unpack(self, buf)
		if self.type > 1500:
			print("Ethernet II")
			# Ethernet II
			print(self.__chg__)
			self._unpack_data(self.data)
		elif self.dst.startswith('\x01\x00\x0c\x00\x00') or \
			 self.dst.startswith('\x03\x00\x0c\x00\x00'):
			# Cisco ISL
			self.vlan = struct.unpack('>H', self.data[6:8])[0]
			self.unpack(self.data[12:])
		elif self.data.startswith('\xff\xff'):
			# Novell "raw" 802.3
			self.type = ETH_TYPE_IPX
			self.data = self.ipx = self._typesw[ETH_TYPE_IPX](self.data[2:])
		else:
			# 802.2 LLC
			self.dsap, self.ssap, self.ctl = struct.unpack('BBB', self.data[:3])
			if self.data.startswith('\xaa\xaa'):
				# SNAP
				self.type = struct.unpack('>H', self.data[6:8])[0]
				self._unpack_data(self.data[8:])
			else:
				# non-SNAP
				dsap = ord(self.data[0])
				if dsap == 0x06: # SAP_IP
					self.data = self.ip = self._typesw[ETH_TYPE_IP](self.data[3:])
				elif dsap == 0x10 or dsap == 0xe0: # SAP_NETWARE{1,2}
					self.data = self.ipx = self._typesw[ETH_TYPE_IPX](self.data[3:])
				elif dsap == 0x42: # SAP_STP
					self.data = self.stp = stp.STP(self.data[3:])
		print("Ethernet unpack end")

	def set_type(cls, t, pktclass):
		cls._typesw[t] = pktclass
	set_type = classmethod(set_type)

	def get_type(cls, t):
		return cls._typesw[t]
	get_type = classmethod(get_type)

# XXX - auto-load Ethernet dispatch table from ETH_TYPE_* definitions
def __load_types():
	"""
	Set ethernet types using globals
	"""
	# avoid RuntimeError because of changing globals.
	# fix https://code.google.com/p/dpkt/issues/detail?id=35
	g = copy.copy(globals())
	for k, v in g.items():
		if k.startswith('ETH_TYPE_'):
			name = k[9:]
			modname = name.lower()
			try:
				mod = __import__(modname, g)
				Ethernet.set_type(v, getattr(mod, name))
			except ImportError:
				continue

if not Ethernet._typesw:
	__load_types()
