package com.nexvary.wificall.platform.gateway

import org.junit.Assert.*
import org.junit.Test

class PairingQrShapeTest {
    private val valid = """{"type":"nexvary-pairing","version":1,"url":"https://example.org","code":"abcdefghijklmnopqrstuvwxyz_0123456789ABCDEFG"}"""
    @Test fun strictJsonShapeAcceptsGeneratedFlatPayload() {
        assertTrue(PairingQrShape.valid(valid))
        assertTrue(PairingQrShape.valid(" \n$valid\t"))
    }
    @Test fun lenientJsonExtensionsAndOversizeInputAreRejected() {
        listOf(valid + "junk", valid.replace('"', '\''), valid.replace(",\"version\"", ",/*x*/\"version\""),
            valid.dropLast(1) + ",}", valid.replace("\"version\":1", "\"version\":01"),
            valid.replace("\"version\":1", "\"version\":[1]"), " ".repeat(4097),
            valid.replace("\"version\":1", "\"version\":\u000c1"))
            .forEach { assertFalse(it.take(40), PairingQrShape.valid(it)) }
    }
}
