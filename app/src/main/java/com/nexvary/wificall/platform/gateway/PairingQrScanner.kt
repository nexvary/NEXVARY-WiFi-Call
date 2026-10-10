package com.nexvary.wificall.platform.gateway

import android.content.Context
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

sealed interface PairingScanResult {
    class Scanned(val raw: String?) : PairingScanResult {
        override fun toString() = "PairingScanResult.Scanned(redacted)"
    }
    data object Cancelled : PairingScanResult
    data object Unavailable : PairingScanResult
}

fun interface PairingQrScanner { suspend fun scan(context: Context): PairingScanResult }

/** Delegates camera use to Google Play services; the app never asks for CAMERA permission. */
object GooglePairingQrScanner : PairingQrScanner {
    override suspend fun scan(context: Context): PairingScanResult {
        if (GoogleApiAvailability.getInstance().isGooglePlayServicesAvailable(context) != ConnectionResult.SUCCESS) {
            return PairingScanResult.Unavailable
        }
        return suspendCancellableCoroutine { continuation ->
            try {
                val options = GmsBarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE).enableAutoZoom().build()
                GmsBarcodeScanning.getClient(context, options).startScan()
                    .addOnSuccessListener { barcode ->
                        if (continuation.isActive) continuation.resume(PairingScanResult.Scanned(barcode.rawValue))
                    }
                    .addOnCanceledListener {
                        if (continuation.isActive) continuation.resume(PairingScanResult.Cancelled)
                    }
                    .addOnFailureListener {
                        if (continuation.isActive) continuation.resume(PairingScanResult.Unavailable)
                    }
            } catch (_: RuntimeException) {
                if (continuation.isActive) continuation.resume(PairingScanResult.Unavailable)
            }
        }
    }
}
