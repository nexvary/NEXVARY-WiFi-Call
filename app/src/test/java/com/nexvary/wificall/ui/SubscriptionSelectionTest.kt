package com.nexvary.wificall.ui

import com.nexvary.wificall.core.SubscriptionRef
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SubscriptionSelectionTest {
    private val first = SubscriptionRef(41, 0, "Carrier A", null, null, null)
    private val second = SubscriptionRef(72, 1, "Carrier B", null, null, null)

    @Test fun dualSimRequiresAnExplicitChoice() {
        assertNull(SubscriptionSelection.resolve(listOf(first, second), null))
    }

    @Test fun bothActiveSubscriptionsCanBeSelected() {
        assertEquals(first, SubscriptionSelection.resolve(listOf(first, second), first.id))
        assertEquals(second, SubscriptionSelection.resolve(listOf(first, second), second.id))
    }

    @Test fun staleSavedIdDoesNotChooseAnUnrelatedSimOnDualSimDevice() {
        assertNull(SubscriptionSelection.resolve(listOf(first, second), 999))
    }

    @Test fun singleActiveSimIsSelectedWithoutAnExplicitChoice() {
        assertEquals(second, SubscriptionSelection.resolve(listOf(second), null))
    }

    @Test fun staleSavedChoiceFallsBackWhenOnlyOneSimRemains() {
        assertEquals(second, SubscriptionSelection.resolve(listOf(second), first.id))
    }

    @Test fun emptySubscriptionsNeverInventASelection() {
        assertNull(SubscriptionSelection.resolve(emptyList(), null))
        assertNull(SubscriptionSelection.resolve(emptyList(), first.id))
    }
}
